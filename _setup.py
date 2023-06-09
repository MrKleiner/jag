

# fuck fuck fuck fuck fuck fuck
# I want to strangle the deranged creator of setup tools
if __name__ == '__main__':
	from pathlib import Path
	import os, shutil, subprocess
	os.system('cls')

	thisdir = Path(__file__).parent
	
	shutil.rmtree(thisdir / 'dist', ignore_errors=True)
	shutil.rmtree(thisdir / 'src' / 'jag_panzer.egg-info', ignore_errors=True)

	for folder in (thisdir / 'src').rglob('*'):
		if folder.name == '__pycache__':
			shutil.rmtree(folder, ignore_errors=True)
	# end
	# 7z a -t7z archive.7z *.txt

	cfg_file = (thisdir / 'setup.cfg').read_text()

	for line in cfg_file.split('\n'):
		if line.strip().startswith('version'):
			ver = line.split('=')[-1].strip()

	os.system('py -m build')
	subprocess.run([
		str(thisdir / 'fuck_pypi' / '7z.exe'),
		'a',
		'-tzip',
		str(thisdir / 'dist' / f'jag_panzer-{ver}-py3-none-any.whl'),
		f"""{str(thisdir / 'src')}\*""",
		"""-xr!jag_panzer.egg-info""",
	])
	os.system('py -m twine upload --repository pypi dist/*')


	shutil.rmtree(thisdir / 'dist', ignore_errors=True)
	shutil.rmtree(thisdir / 'src' / 'jag_panzer.egg-info', ignore_errors=True)






