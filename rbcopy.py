import shutil, sys
from pathlib import Path


thisdir = Path(__file__).parent
site_packages = Path(sys.executable).parent / 'Lib' / 'site-packages'


shutil.rmtree(site_packages / 'jag_panzer')

shutil.copytree(thisdir / 'src' / 'jag_panzer', site_packages / 'jag_panzer')
