"""The t3db schema (`nhl_game-meta.xml`): table and field names, value ranges and save groups.

The schema is read from the user's own game files at runtime; Overtime never ships it.
"""
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class FieldMeta:
    name: str
    short: str
    is_string: bool
    depth: int  # bits
    low: int
    high: int
    key: bool


@dataclass
class TableMeta:
    name: str
    short: str
    savegroups: tuple
    fields: dict = field(default_factory=dict)  # shortname -> FieldMeta

    def field_by_name(self, name):
        for f in self.fields.values():
            if f.name == name:
                return f
        raise KeyError(f"{self.name}: no field {name!r}")


@dataclass
class Schema:
    name: str
    version: int
    tables: dict  # shortname -> TableMeta

    def by_name(self, name):
        for t in self.tables.values():
            if t.name == name:
                return t
        raise KeyError(f"no table {name!r}")


def parse_schema(xml_bytes):
    root = ET.fromstring(xml_bytes)
    tables = {}
    for t in root.iter('table'):
        groups = tuple(g for g in t.get('savegroups', '').split(',') if g)
        meta = TableMeta(t.get('name'), t.get('shortname'), groups)
        for f in t.iter('field'):
            meta.fields[f.get('shortname')] = FieldMeta(
                name=f.get('name'),
                short=f.get('shortname'),
                is_string=f.get('type') == 'FIELDTYPE_STRING',
                depth=int(f.get('depth')),
                low=int(f.get('rangelow', '0')),
                high=int(f.get('rangehigh', '0')),
                key=f.get('key') == 'True',
            )
        tables[meta.short] = meta
    return Schema(root.get('name'), int(root.get('version', '0')), tables)


def load_schema(path):
    with open(path, 'rb') as fh:
        return parse_schema(fh.read())
