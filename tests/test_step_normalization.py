from __future__ import annotations

from mesh2param.validation import normalize_step_bytes


def _step_payload(first: str, second: str, *, wrapped: bool = False) -> bytes:
    point = f"#1 = CARTESIAN_POINT('',({first},{second},-6.077511700175E-16));"
    if wrapped:
        point = point.replace(f",{second},", f",\n  {second},")
    return (
        "ISO-10303-21;\n"
        "HEADER;\n"
        "FILE_NAME('unstable','2026-07-27T20:00:00',(''),(''),"
        "'Open CASCADE STEP translator 7.9 41',"
        "'Open CASCADE STEP translator 7.9 42','');\n"
        "ENDSEC;\n"
        "DATA;\n"
        f"{point}\n"
        "ENDSEC;\n"
        "END-ISO-10303-21;\n"
    ).encode()


def test_step_normalization_removes_sub_kernel_numeric_drift() -> None:
    first = normalize_step_bytes(
        _step_payload("9.317050489215", "4.164777149519"),
        model_name="shaft-collar",
    )
    second = normalize_step_bytes(
        _step_payload("9.317050489216", "4.164777149518", wrapped=True),
        model_name="shaft-collar",
    )

    assert first == second
    assert b"9.31705048922" in first
    assert b"4.16477714952" in first
    assert b"-6.07751170018E-16" in first


def test_step_normalization_handles_large_real_literals() -> None:
    normalized = normalize_step_bytes(
        _step_payload("12345678901234567890.123456789012", "4.164777149519"),
        model_name="large-model",
    )

    assert b"12345678901234567890.12345678901" in normalized
