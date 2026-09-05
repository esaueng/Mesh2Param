from __future__ import annotations

import asyncio
import logging
import shutil
import stat
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from .config import Settings
from .db import Repository
from .storage import LocalCAS

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GarbageCollectionResult:
    metadata_blobs: int = 0
    filesystem_blobs: int = 0
    job_directories: int = 0
    upload_files: int = 0


class StorageGarbageCollector:
    def __init__(self, repository: Repository, storage: LocalCAS, settings: Settings) -> None:
        self.repository = repository
        self.storage = storage
        self.settings = settings

    def run_once(self, *, cutoff: datetime | None = None) -> GarbageCollectionResult:
        threshold = cutoff or datetime.now(UTC) - timedelta(days=self.settings.retention_days)
        threshold_epoch = threshold.timestamp()
        with self.storage.publication_lock(exclusive=True):
            metadata_blobs = 0
            for digest in self.repository.orphan_blob_candidates_before(
                threshold,
                limit=self.settings.garbage_collection_batch_size,
            ):
                self.storage.delete_blob(digest)
                if self.repository.delete_orphan_blob_metadata(digest):
                    metadata_blobs += 1

            known = self.repository.known_blob_digests()
            filesystem_blobs = 0
            for digest, modified_at in self.storage.iter_blobs():
                if digest not in known and modified_at < threshold_epoch:
                    filesystem_blobs += int(self.storage.delete_blob(digest))

        return GarbageCollectionResult(
            metadata_blobs=metadata_blobs,
            filesystem_blobs=filesystem_blobs,
            job_directories=self._sweep_job_directories(threshold_epoch),
            upload_files=self._sweep_upload_files(threshold_epoch),
        )

    def _sweep_job_directories(self, threshold_epoch: float) -> int:
        active = self.repository.active_workdir_tokens()
        removed = 0
        self.settings.jobs_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for candidate in self.settings.jobs_root.iterdir():
            status = candidate.lstat()
            token = candidate.name.partition("-")[0]
            if (
                stat.S_ISDIR(status.st_mode)
                and not stat.S_ISLNK(status.st_mode)
                and token not in active
                and status.st_mtime < threshold_epoch
            ):
                shutil.rmtree(candidate)
                removed += 1
        return removed

    def _sweep_upload_files(self, threshold_epoch: float) -> int:
        removed = 0
        self.settings.upload_staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for candidate in self.settings.upload_staging_root.iterdir():
            status = candidate.lstat()
            if (
                candidate.name.startswith("upload-")
                and candidate.name.endswith(".part")
                and (stat.S_ISREG(status.st_mode) or stat.S_ISLNK(status.st_mode))
                and status.st_mtime < threshold_epoch
            ):
                candidate.unlink()
                removed += 1
        return removed


async def garbage_collection_loop(
    collector: StorageGarbageCollector,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(
                stop.wait(),
                timeout=collector.settings.garbage_collection_interval_seconds,
            )
            return
        except TimeoutError:
            pass
        try:
            result = await asyncio.to_thread(collector.run_once)
            if any(asdict(result).values()):
                LOGGER.info("garbage_collection_complete", extra={"result": asdict(result)})
        except Exception:
            LOGGER.exception("garbage_collection_failed")
