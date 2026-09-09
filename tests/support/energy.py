"""Small energy-file fixtures with explicit terms and frame values."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from mda_xdrlib.xdrlib import Packer


def write_energy(
    path: Path, data: Mapping[str, Sequence[float]], units: Mapping[str, str],
) -> None:
    packer = Packer()
    names = [name for name in data if name != "Time"]
    packer.pack_int(-55555)
    packer.pack_int(5)
    packer.pack_int(len(names))
    for name in names:
        packer.pack_string(name.encode("ascii"))
        packer.pack_string(units[name].encode("ascii"))
    for frame, time in enumerate(data["Time"]):
        packer.pack_float(-2e10)
        packer.pack_int(-7777777)
        packer.pack_int(5)
        packer.pack_double(float(time))
        packer.pack_hyper(frame)
        packer.pack_int(0)
        packer.pack_hyper(1)
        packer.pack_double(0)
        for value in (len(names), 0, 0, len(names) * 4, 0, 0):
            packer.pack_int(value)
        for name in names:
            packer.pack_float(float(data[name][frame]))
    path.write_bytes(packer.get_buffer())
