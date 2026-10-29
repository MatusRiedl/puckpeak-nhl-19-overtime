"""Reading mode saves: a Franchise / Season file is a chain of LZ4 chunks whose database chunks are parsed."""
import os

from overtime_core import lz4f, modesave, savefile
from test_tdb import SCHEMA, make_db


def write_folder(path, entries):
    os.makedirs(path)
    index, data = savefile.build([savefile.SaveEntry(n, bytes(8), p) for n, p in entries])
    with open(os.path.join(path, 'INDEX'), 'wb') as f:
        f.write(index)
    with open(os.path.join(path, 'DATA'), 'wb') as f:
        f.write(data)


def test_chained_file_and_its_database_chunk(tmp_path):
    db = make_db().to_bytes()
    chain = b'\x01' + lz4f.encode(b'objects') + b'\x01' + lz4f.encode(db) + b'raw tail'
    folder = str(tmp_path / 'BeAGM0')
    write_folder(folder, [('__SaveLoadMetaData', savefile.pack(b'{"SeasonYear": 20180618}')),
                          ('BeAGM', savefile.pack(chain))])
    save = modesave.read(folder, SCHEMA)
    f = save.files['BeAGM']
    assert f.chunks == [b'objects', db] and f.rest == b'raw tail' and len(f.chunk_dbs) == 1
    assert list(save.databases) == ['BeAGM#0'] and save.meta == {'SeasonYear': 20180618}
    assert save.table(SCHEMA, 'players').count == 2
    assert any('2 chunks' in line for line in modesave.summary(folder, SCHEMA))
    assert modesave.list_saves(str(tmp_path)) == ['BeAGM0']


def test_plain_database_file(tmp_path):
    db = make_db().to_bytes()
    folder = str(tmp_path / 'RosterCustom0')
    write_folder(folder, [('Roster', savefile.pack(db + b'trailer'))])
    f = modesave.read(folder, SCHEMA).files['Roster']
    assert f.db is not None and f.trailer == b'trailer' and f.chunks == []
