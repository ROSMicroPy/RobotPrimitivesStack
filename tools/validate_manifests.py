"""Validate deployment and service documents against Somatic Mesh schemas."""
import json
from pathlib import Path

import jsonschema
from referencing import Registry, Resource
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    schemas = [json.loads(path.read_text()) for path in
               (ROOT / 'SomaticMesh/spec').glob('*-manifest.schema.json')]
    registry = Registry().with_resources((schema['$id'], Resource.from_contents(schema))
                                         for schema in schemas)
    validators = {}
    for schema in schemas:
        jsonschema.Draft202012Validator.check_schema(schema)
        kind = schema['properties']['manifest']['const']
        validators[kind] = jsonschema.Draft202012Validator(schema, registry=registry)
    count = 0
    for base in (ROOT / 'SomaticMesh', ROOT / 'examples'):
        for path in sorted(base.rglob('*')):
            if path.suffix not in ('.json', '.yaml'):
                continue
            text = path.read_text()
            if 'somatic.node/v1' not in text and 'somatic.service/v1' not in text:
                continue
            document = json.loads(text) if path.suffix == '.json' else yaml.safe_load(text)
            if not isinstance(document, dict) or document.get('manifest') not in validators:
                continue
            errors = list(validators[document['manifest']].iter_errors(document))
            if errors:
                raise ValueError(str(path.relative_to(ROOT)) + ': ' + '\n'.join(
                    '/'.join(map(str, error.path)) + ': ' + error.message for error in errors))
            count += 1
    if not count:
        raise AssertionError('no manifests found')
    print('Validated {} node and service manifests.'.format(count))


if __name__ == '__main__':
    main()
