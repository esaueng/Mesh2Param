from __future__ import annotations

import os
import select
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import timedelta
from pathlib import Path

import pytest
from mesh2param_api.config import Settings
from mesh2param_api.db import Database, Repository
from mesh2param_api.db.models import ArtifactBlob, utc_now
from mesh2param_api.maintenance import StorageGarbageCollector
from mesh2param_api.storage import LocalCAS, UnsafeStoragePathError


@pytest.mark.parametrize("metadata_exists", [False, True])
def test_gc_waits_for_blob_reference_commit(tmp_path: Path, metadata_exists: bool) -> None:
    settings = Settings(environment="test", data_dir=tmp_path)
    database = Database(settings)
    database.migrate()
    repo = Repository(database)
    store = LocalCAS(settings.storage_root)
    blob = store.put_bytes(b"reuploaded source")
    old = utc_now() - timedelta(days=60)
    os.utime(blob.path, (old.timestamp(), old.timestamp()))
    if metadata_exists:
        with database.sessions.begin() as session:
            session.add(
                ArtifactBlob(
                    sha256=blob.sha256,
                    byte_size=blob.byte_size,
                    media_type="model/stl",
                    storage_key=str(blob.path.relative_to(store.root)),
                    created_at=old,
                )
            )
    project = repo.create_project("Reupload", "mm")
    collector = StorageGarbageCollector(repo, LocalCAS(settings.storage_root), settings)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with store.publication_lock():
                store.put_bytes(b"reuploaded source")
                collection = pool.submit(collector.run_once)
                # Both metadata-backed and filesystem-only orphans must be protected
                # in the interval between deduplicated publication and reference commit.
                with pytest.raises(FutureTimeout):
                    collection.result(timeout=0.2)
                repo.create_source_asset(
                    project["id"],
                    project["revision"],
                    original_filename="part.stl",
                    format_name="stl",
                    encoding="binary",
                    blob={
                        "sha256": blob.sha256,
                        "byteSize": blob.byte_size,
                        "mediaType": "model/stl",
                        "storageKey": str(blob.path.relative_to(store.root)),
                    },
                    declared_units="mm",
                    units_confirmed=True,
                    scale_factor=1,
                )
            result = collection.result(timeout=10)
        assert result.metadata_blobs == result.filesystem_blobs == 0
        assert store.contains(blob.sha256)
        assert repo.get_source_asset(project["id"])["sha256"] == blob.sha256
    finally:
        database.dispose()


def test_publication_lock_serializes_separate_processes(tmp_path: Path) -> None:
    store = LocalCAS(tmp_path)
    script = """
import sys
from mesh2param_api.storage import LocalCAS
store = LocalCAS(sys.argv[1])
print('waiting', flush=True)
with store.publication_lock(exclusive=True):
    print('acquired', flush=True)
"""
    with store.publication_lock():
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", script, str(tmp_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert process.stdout is not None
            assert select.select([process.stdout], [], [], 10)[0]
            assert process.stdout.readline().strip() == "waiting"
            assert not select.select([process.stdout], [], [], 0.2)[0]
        except BaseException:
            process.kill()
            process.communicate()
            raise
    try:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        assert stdout.strip() == "acquired"
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_publication_lock_rejects_symlinks_and_releases_after_failure(tmp_path: Path) -> None:
    store = LocalCAS(tmp_path)
    with pytest.raises(RuntimeError), store.publication_lock():
        raise RuntimeError("publication aborted")
    with store.publication_lock(exclusive=True):
        pass
    lock = tmp_path / ".publication.lock"
    lock.unlink()
    target = tmp_path / "do-not-touch"
    target.write_text("unchanged")
    lock.symlink_to(target)
    with pytest.raises((OSError, UnsafeStoragePathError)), store.publication_lock():
        pytest.fail("symlink lock was opened")
    assert target.read_text() == "unchanged"
