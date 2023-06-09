

if __name__ == '__main__':
	from pathlib import Path
	import os, shutil
	os.system('cls')

	thisdir = Path(__file__).parent
	
	shutil.rmtree(thisdir / 'dist', ignore_errors=True)
	shutil.rmtree(thisdir / 'src' / 'jag_panzer.egg-info', ignore_errors=True)

	for folder in (thisdir / 'src').rglob('*'):
		if folder.name == '__pycache__':
			shutil.rmtree(folder, ignore_errors=True)

	os.system('py -m build')
	os.system('py -m twine upload --repository testpypi dist/*')


	shutil.rmtree(thisdir / 'dist', ignore_errors=True)
	shutil.rmtree(thisdir / 'src' / 'jag_panzer.egg-info', ignore_errors=True)






