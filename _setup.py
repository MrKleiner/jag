

# fuck fuck fuck fuck fuck fuck
# I want to strangle the deranged creator of setup tools
if __name__ == '__main__':
	from pathlib import Path
	from szipper import szip
	import os, shutil, subprocess
	os.system('cls')

	thisdir = Path(__file__).parent
	archiver = szip(thisdir / 'fuck_pypi' / '7z.exe')
	
	shutil.rmtree(thisdir / 'dist', ignore_errors=True)
	shutil.rmtree(thisdir / 'src' / 'jag_panzer.egg-info', ignore_errors=True)

	# delete all caches
	for folder in (thisdir / 'src').rglob('*'):
		if folder.name == '__pycache__':
			shutil.rmtree(folder, ignore_errors=True)

	# Build the project
	os.system('py -m build')

	# append data to the wheel file
	archiver.pack(
		f"""{str(thisdir / 'src')}\*""",
		str([ver for ver in (thisdir / 'dist').glob('*.whl')][0]),
		['jag_panzer.egg-info'],
		open_as='zip',
		append_data=True,
	)

	# Upload project to the pypi.org
	os.system('py -m twine upload --repository pypi dist/*')


	shutil.rmtree(thisdir / 'dist', ignore_errors=True)
	shutil.rmtree(thisdir / 'src' / 'jag_panzer.egg-info', ignore_errors=True)






