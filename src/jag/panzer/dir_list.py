class dirlist:
	"""simple directory lister"""
	def __init__(self, srv_res):
		"""
		Init compiles a very simple document for later use
		"""
		from bs4 import BeautifulSoup
		import base64
		import jag_util

		self.srv_res = srv_res

		# shortcut to the dir_listing folder in the assets
		assets_dir = srv_res.sysroot / 'assets' / 'dir_listing'

		# Parse the template to populate it with scripts and styles
		doc_base = BeautifulSoup(
			(assets_dir / 'base.html').read_bytes(),
			'html.parser'
		)

		# Load css file and add icons to it
		css_base = jag_util.multireplace(
			(assets_dir / 'style.css').read_bytes(),
			[
				(b'$$folder_icon_b64', base64.b64encode((assets_dir / 'dir_icon.svg').read_bytes())),
				(b'$$file_icon_b64', base64.b64encode((assets_dir / 'file_icon.svg').read_bytes())),
				(b'$$dl_icon_b64', base64.b64encode((assets_dir / 'download_icon.svg').read_bytes())),
			]
		)
		# Append css to the body
		style_tag = doc_base.new_tag('style', type='text/css')
		style_tag.string = css_base.decode()
		doc_base.body.append(style_tag)

		# add script to the file
		script_tag = doc_base.new_tag('script', type='text/javascript')
		script_tag.string = (assets_dir / 'script.js').read_text()
		doc_base.body.append(script_tag)

		# split the document into 2 parts
		self.doc_a, self.doc_b = str(doc_base).encode().split(b'$$speed_split')


	def dir_as_html(self, tgt_dir):
		# import io
		# from pathlib import Path
		io = self.srv_res.pylib.io
		Path = self.srv_res.pylib.Path

		# dir to list
		tgt_dir = Path(tgt_dir)

		# yield the beginning of the document
		# important todo: there's certainly a better way of doing this,
		# like having predefined buffers or something
		yield self.doc_a

		# raw glob result
		dirlist = list(tgt_dir.glob('*'))
		# sort by name
		dirlist.sort(key=lambda a: a.name.lower())
		# sort by type (folder/file)
		dirlist.sort(key=lambda a: int(a.is_file()))


		# yield listed entries one by one
		# in a form of html
		for entry in dirlist:
			yield (
				f"""
					<div class="list_entry" {'file_entry' if entry.is_file() else 'dir_entry'}>
						<a
							class="actual_link"
							href="/{entry.relative_to(self.srv_res.doc_root).as_posix()}"
						>{entry.name}</a>
						<a download class="dl_button" href="/{entry.relative_to(self.srv_res.doc_root).as_posix()}"></a>
					</div>
				""".encode()
			)

		# yield the end of the document
		yield self.doc_b

		# return list_buf






