"""Build a self-contained GitHub Pages demo without changing Docker assets."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'scada/web'
target = ROOT / 'pages'
target.mkdir(exist_ok=True)
html = (source / 'index.html').read_text()
html = html.replace('href="/style.css"', 'href="./style.css"')
html = html.replace('src="/app.js"', 'src="./app.js"')
html = html.replace('<script src="./app.js"', '<script src="./demo-engine.js" defer></script><script src="./app.js"')
html = html.replace('href="/"', 'href="./"')
html = html.replace('src="/plc-', 'src="./plc-')
html = html.replace('Independent automation portfolio <span>·</span> Fictional Ghanaian training facility · All data simulated', 'Browser-only simulation <span>·</span> Independent Tema Utilities Lab · All data simulated')
html = html.replace('SQL STORED', 'BROWSER STORED')
html = html.replace('Versioned recipe library', 'Browser recipe library')
html = html.replace('Saved versions remain unchanged. Each batch keeps its own recipe snapshot.',
                    'Recipes and history stay in this browser when storage is available. Full SQL integration is included in the GitHub source.')
html = html.replace('PYTHON CONTROLS · MODBUS TCP · MQTT · SQL HISTORIAN',
                    'BROWSER SIMULATION · LOCAL HISTORY · DOCKER STACK IN SOURCE')
html = html.replace('Fictional training facility · Tema, Ghana',
                    '<a href="https://github.com/Ekow244/tema-utilities-scada" target="_blank" rel="noopener">View source on GitHub ↗</a>')
html = html.replace('A live view of your thermal batch process.', 'An interactive simulation of a thermal utilities skid.')
(target / 'index.html').write_text(html)
for name in ('app.js', 'style.css', 'demo-engine.js', 'plc-engine.js', 'plc-panel.js', 'plc-program.json'):
    shutil.copy2(source / name, target / name)
shutil.copytree(source / 'training', target / 'training', dirs_exist_ok=True)
(target / '.nojekyll').touch()
print(f'Built {target}')
