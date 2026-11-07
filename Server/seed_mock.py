"""Explicitly install upstream mock events without overwriting existing files."""
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    destination = root / 'Data_Cache/events'
    destination.mkdir(parents=True, exist_ok=True)
    for source in sorted((root / 'Pipeline/Mock_Event').glob('*.json')):
        target = destination / source.name
        try:
            with target.open('x', encoding='utf-8') as output:
                output.write(source.read_text(encoding='utf-8'))
        except FileExistsError:
            print(f'Already exists: {target.name}')
        else:
            print(f'Copied: {target.name}')


if __name__ == '__main__':
    main()
