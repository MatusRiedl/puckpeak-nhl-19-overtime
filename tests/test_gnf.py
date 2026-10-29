"""GNF textures: tiling round trip, new textures shaped like a template, the game's own textures read back."""
import os
import random
import struct

import pytest

from overtime_core import eb, gamefiles, gnf


def template(w, h, fmt='BC1', num='UNORM', mips=1, pitch=None):
    """A GNF file like the game's (thin 1D tiling, data at 0x100) with random data."""
    words = [0] * 8
    words[1] = (gnf.DFMT[fmt] << 20) | (gnf.NFMT[num] << 26)
    words[2] = (w - 1) | ((h - 1) << 14)
    words[3] = ((mips - 1) << 16) | (gnf.TILE_THIN_1D << 20) | (9 << 28)
    words[4] = ((pitch or w) - 1) << 13
    t = gnf.Texture(words)
    size = sum(n for *_, n in gnf.mip_layout(t))
    words[7] = size
    head = bytearray(0x100)
    head[:4] = gnf.MAGIC
    struct.pack_into('<I', head, 4, 0xf8)
    head[8:12] = bytes((2, 1, 8, 0))
    struct.pack_into('<I', head, 12, 0x100 + size)
    struct.pack_into('<8I', head, 16, *words)
    rnd = random.Random(w * h + mips)
    return bytes(head) + bytes(rnd.getrandbits(8) for _ in range(size))


@pytest.mark.parametrize('w,h,fmt,mips,pitch', [(64, 64, 'BC1', 1, None), (200, 120, 'BC7', 1, 224),
                                                 (256, 256, 'BC3', 9, None), (48, 16, '8_8_8_8', 1, 64)])
def test_retile_detile_round_trip(w, h, fmt, mips, pitch):
    raw = template(w, h, fmt, mips=mips, pitch=pitch)
    g = gnf.Gnf(raw)
    t = g.texture
    assert (t.width, t.height, t.fmt, t.mips, t.tile) == (w, h, fmt, mips, 13)
    lin = gnf.detile(t, g.data())
    bpe, blk = gnf.FMT_BPE[fmt]
    assert len(lin[0]) == ((w + blk - 1) // blk) * ((h + blk - 1) // blk) * bpe
    if pitch is None and mips == 1:  # padding (pitch, small mips) is random here and not kept
        assert gnf.retile(t, lin) == g.data()
    again = gnf.from_mips(raw, lin)
    assert gnf.detile(gnf.Gnf(again).texture, gnf.Gnf(again).data()) == lin


def test_from_mips_checks_sizes():
    raw = template(64, 64, 'BC1', mips=2)
    with pytest.raises(gnf.GnfError):
        gnf.from_mips(raw, [b'\0' * 2048])
    with pytest.raises(gnf.GnfError):
        gnf.from_mips(raw, [b'\0' * 100, b'\0' * 512])


def test_make_bc7_template_becomes_bc3():
    pil = pytest.importorskip('PIL.Image')
    raw = template(128, 128, 'BC7')
    img = pil.new('RGBA', (300, 300), (200, 30, 40, 255))
    out = gnf.make(raw, img)
    g = gnf.Gnf(out)
    assert g.texture.fmt == 'BC3' and g.texture.num == 'UNORM' and len(out) == len(raw)
    assert g.file_size == len(out)
    px = gnf.to_image(out).getpixel((64, 64))
    assert abs(px[0] - 200) < 8 and abs(px[1] - 30) < 8 and px[3] == 255


def test_make_keeps_mips_and_srgb():
    pil = pytest.importorskip('PIL.Image')
    raw = template(256, 256, 'BC1', 'SRGB', mips=9)
    out = gnf.make(raw, pil.new('RGB', (256, 256), (10, 120, 250)))
    t = gnf.Gnf(out).texture
    assert (t.fmt, t.num, t.mips, len(out)) == ('BC1', 'SRGB', 9, len(raw))
    assert gnf.to_image(out, level=8).size == (1, 1)


@pytest.mark.game
def test_game_textures_round_trip(game_dir):
    """A UI logo (BC7, 1 mip) and a 3D jersey colour map (BC1 sRGB, full mip chain) read back byte for byte."""
    want = {'nhl/ui/kettle_assets/teamlogos/large/t22.gnf',
            'nhl/data/kettle/rendering/characters/player/jersey_adidas_arizona_home_cm.gnf'}
    found = {}
    for big in gamefiles.archives(game_dir):
        with eb.EbArchive(big) as arc:
            for p in want & set(arc.entries):
                found[p] = arc.read(p)
    assert set(found) == want
    for raw in found.values():
        g = gnf.Gnf(raw)
        assert gnf.retile(g.texture, gnf.detile(g.texture, g.data())) == g.data()
        assert gnf.from_mips(raw, gnf.detile(g.texture, g.data())) == raw
    assert gnf.info(found['nhl/ui/kettle_assets/teamlogos/large/t22.gnf'])['format'] == 'BC7'
    cm = gnf.info(found['nhl/data/kettle/rendering/characters/player/jersey_adidas_arizona_home_cm.gnf'])
    assert (cm['format'], cm['num'], cm['width'], cm['mips']) == ('BC1', 'SRGB', 2048, 12)
    assert os.path.basename(game_dir)
