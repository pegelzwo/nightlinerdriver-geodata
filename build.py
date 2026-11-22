#!/usr/bin/env python3
"""Stream OSM motorway LineStrings from osmium GeoJSONSeq into per-road gzip bundles.

This is segment preparation, NOT route assembly, carriageway verification or chainage.
"""
import gzip
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROAD_RE = re.compile(r"^A\s*([0-9]{1,3})([a-z]?)$", re.I)

def main(source: Path, target: Path):
    target.mkdir(parents=True, exist_ok=True)
    grouped = defaultdict(list)
    skipped = 0
    with source.open('r', encoding='utf-8') as stream:
        for line in stream:
            line = line.strip().lstrip('\x1e')
            if not line:
                continue
            try:
                feat = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            props = feat.get('properties') or {}
            if props.get('highway') != 'motorway':
                continue
            geom = feat.get('geometry') or {}
            if geom.get('type') != 'LineString':
                skipped += 1
                continue
            coords = geom.get('coordinates')
            if not isinstance(coords, list) or len(coords) < 2:
                skipped += 1
                continue
            raw_id = str(feat.get('id') or props.get('@id') or '')
            id_match = re.search(r'(?:way/)?([1-9][0-9]*)$', raw_id)
            if not id_match:
                skipped += 1
                continue
            # OSM ref may include multiple road refs separated by semicolons.
            refs = set()
            for ref in str(props.get('ref') or '').split(';'):
                match = ROAD_RE.fullmatch(ref.strip())
                if match:
                    refs.add('A' + match.group(1) + match.group(2).lower())
            if not refs:
                skipped += 1
                continue
            record = {'id': int(id_match.group(1)), 'coordinates': coords,
                      'oneway': props.get('oneway'), 'name': props.get('name')}
            for ref in refs:
                grouped[ref].append(record)
    manifest = {
        'schema_version': 1,
        'source': 'Geofabrik Germany OpenStreetMap extract',
        'license': 'Open Database License (ODbL)',
        'attribution': '© OpenStreetMap contributors',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'note': 'Unverbundene Autobahnsegmente; keine geprüften Richtungsfahrbahnen oder Kilometerangaben.',
        'roads': {}, 'roads_count': len(grouped),
        'segments_count': sum(map(len, grouped.values())), 'skipped': skipped
    }
    for road in sorted(grouped, key=lambda x: (int(re.search(r'\d+', x).group()), x)):
        filename = road + '.json.gz'
        data = {'road': road, 'segments': grouped[road]}
        with gzip.open(target / filename, 'wt', encoding='utf-8', compresslevel=6) as f:
            json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
        manifest['roads'][road] = {'file': filename, 'segments': len(grouped[road]),
                                    'bytes': (target / filename).stat().st_size}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Exported {manifest['roads_count']} roads and {manifest['segments_count']} segments")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('Usage: build.py INPUT.geojsonseq OUTPUT_DIRECTORY')
    main(Path(sys.argv[1]), Path(sys.argv[2]))
