from pathlib import Path
from threading import Event

import pytest

from mdhelper.core.errors import JobCancelled
from mdhelper.core.workspace import DataLayout
from mdhelper.services.workspace import WorkspaceDocument


def test_binary_open_defers_records_and_pages_are_cached(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(b"\0")
    visited = []
    closed = []

    class Reader:
        layout = DataLayout()

        def __init__(self, _path):
            pass

        def records(self, _cancel):
            for index in range(1000):
                visited.append(index)
                yield (("data", str(index), str(index * 2)),)

        def close(self):
            closed.append(True)

    monkeypatch.setattr("mdhelper.backends.mdanalysis.workspace.BinaryDocument", Reader)
    with WorkspaceDocument(path) as document:
        assert not visited
        assert not closed
        assert document.rows == 0
        first = document.page(0, 16)
        assert visited == list(range(16))
        assert not first.complete
        assert document.page(0, 16) == first
        assert len(visited) == 16
        last = document.page(990, 16)
        assert last.complete
        assert last.rows[-1] == ("data", "999", "1998")
    assert closed == [True]


@pytest.mark.parametrize("suffix", ["xtc", "trr"])
def test_trajectory_open_does_not_scan_offsets_or_decode_later_frames(
    tmp_path: Path, monkeypatch, suffix: str,
) -> None:
    import MDAnalysis as mda
    from MDAnalysis.coordinates.XDR import XDRBaseReader

    path = tmp_path / f"trajectory.{suffix}"
    universe = mda.Universe.empty(257, trajectory=True)
    with mda.Writer(str(path), n_atoms=len(universe.atoms)) as writer:
        for frame in range(5):
            universe.atoms.positions = frame + 1
            universe.trajectory.ts.time = frame * 3
            writer.write(universe)

    def reject_index(*_args, **_kwargs):
        raise AssertionError("Opening a sequential stream must not build a frame index")

    from mdhelper.backends.mdanalysis.trajectory import _CachedOffsets

    monkeypatch.setattr(XDRBaseReader, "_load_offsets", reject_index)
    monkeypatch.setattr(_CachedOffsets, "_load_offsets", reject_index)
    from mdhelper.backends.mdanalysis.workspace.streams import SequentialXdr

    advance = SequentialXdr._advance
    decoded = []

    def read_frame(self):
        step = advance(self)
        decoded.append(step.frame)
        return step

    monkeypatch.setattr(SequentialXdr, "_advance", read_frame)
    with WorkspaceDocument(path) as document:
        assert document.file.parsed
        assert document.rows == 0
        assert decoded == [0]
        document.page(0, 1)
        assert decoded == [0]
        rows = []
        while True:
            page = document.page(len(rows), 128)
            rows.extend(page.rows)
            if page.complete:
                break
        assert decoded == list(range(5))
        last = [row for row in rows if row[0] == "frames/4/positions"]
        assert len(last) == len(universe.atoms)
        assert float(last[-1][-1].strip("[]").split(",")[-1]) == pytest.approx(5)
    assert not list(tmp_path.glob(".*offset*"))


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_large_text_is_read_in_bounded_blocks_without_partial_saves(
    tmp_path: Path, newline: str,
) -> None:
    path = tmp_path / "notes.txt"
    text = ("a" * 65535 + chr(233) + newline) * 20
    path.write_bytes(text.encode("utf-8"))
    with WorkspaceDocument(path) as document:
        assert not document.file.editable
        assert document.file.parsed
        assert document.file.text == ""
        assert document.rows == 0
        first = document.page(0, 1)
        assert not first.complete
        assert len(first.rows[0][-1]) <= 65536
        rows = list(first.rows)
        offset = len(rows)
        while True:
            page = document.page(offset, 2)
            rows.extend(page.rows)
            offset += len(page.rows)
            if page.complete:
                break
        assert "".join(row[-1] for row in rows) == text
    assert path.read_bytes() == text.encode("utf-8")


def test_large_text_save_is_rejected_without_touching_original(tmp_path: Path) -> None:
    from mdhelper.core.errors import ConfigurationError
    from mdhelper.services.workspace import save_workspace_text

    path = tmp_path / "large.txt"
    content = b"original\n" * 150_000
    path.write_bytes(content)
    with pytest.raises(ConfigurationError):
        save_workspace_text(path, "only the loaded part")
    assert path.read_bytes() == content


def test_energy_stream_reads_only_requested_frames_and_reports_truncation(
    tmp_path: Path, monkeypatch,
) -> None:
    from mdhelper.backends.mdanalysis.workspace.streams import EnergyStream
    from tests.support.energy import write_energy

    path = tmp_path / "energy.edr"
    data = {"Time": list(range(600)), "signal": list(range(600))}
    write_energy(path, data, {"signal": "kJ/mol"})
    original = EnergyStream.do_enx
    frames = []

    def read(self):
        frames.append(True)
        return original(self)

    monkeypatch.setattr(EnergyStream, "do_enx", read)
    with WorkspaceDocument(path) as document:
        assert document.file.parsed
        assert len(frames) == 1
        assert document.page(0, 1).rows == (("0", "0.0", "0.0"),)
        assert len(frames) == 1
        assert document.page(10, 1).rows == (("10", "10.0", "10.0"),)
        assert len(frames) == 11
        document.page(0, 1)
        assert len(frames) == 11
    path.write_bytes(path.read_bytes()[:-2])
    with WorkspaceDocument(path) as document:
        assert document.file.parsed
        with pytest.raises(OSError):
            document.page(599, 1)
        assert document.store is None
    path.unlink()


@pytest.mark.parametrize("content", [b"\0data", b"\x7f\xff\xff\xff"])
def test_invalid_energy_counts_fail_without_allocating_records(
    tmp_path: Path, content: bytes,
) -> None:
    path = tmp_path / "invalid.edr"
    path.write_bytes(content)
    with WorkspaceDocument(path) as document:
        assert not document.file.parsed and not document.file.editable
        assert document.file.message
        assert document.rows == 0
    path.unlink()


def test_lazy_page_cancellation_closes_resources(tmp_path: Path) -> None:
    path = tmp_path / "large.txt"
    path.write_bytes(b"a" * 2_000_000)
    cancel = Event()
    with WorkspaceDocument(path, cancel) as document:
        document.page(0, 1)
        cancel.set()
        with pytest.raises(JobCancelled):
            document.page(1, 1)
        assert document.store is None


def test_image_decode_limit_does_not_prevent_header_inspection(tmp_path: Path) -> None:
    from PIL import Image

    path = tmp_path / "large.png"
    with Image.new("1", (8192, 4097)) as source:
        source.save(path)
    with WorkspaceDocument(path) as document:
        assert document.file.image is not None
        assert document.file.image.width == 8192
        with pytest.raises(ValueError):
            document.image((400, 300))
    path.unlink()


@pytest.mark.parametrize("format", ["PNG", "JPEG", "GIF", "BMP", "TIFF", "WEBP"])
def test_images_are_detected_by_content_and_decoded_on_demand(tmp_path: Path, format: str) -> None:
    from PIL import Image

    path = tmp_path / "picture.data"
    Image.new("RGB", (320, 160), (20, 40, 60)).save(path, format=format)
    with WorkspaceDocument(path) as document:
        info = document.file.image
        assert info is not None
        assert (info.width, info.height, info.format) == (320, 160, format)
        assert not document.file.editable and not document.file.parsed
        assert document.rows == 0 and document.store is None
        pixels = document.image((80, 80))
        assert (pixels.width, pixels.height) == (80, 40)
        assert len(pixels.rgba) == pixels.width * pixels.height * 4
    path.unlink()
