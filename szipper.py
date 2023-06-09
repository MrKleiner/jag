

class szip:
	"""Easily create and unpack 7z archives"""
	def __init__(self, exe_loc):
		from pathlib import Path
		import subprocess
		self.Path = Path
		self.sp = subprocess
		self.exe = Path(exe_loc)


	def pack(self, input_data, output_loc, exclude=None, compression_rate=9, chunk_size=None, dict_size='12m', word_size='273', block_size='2g', append_data=False, open_as=None, echo=False):
		exclude = exclude or []
		zip_prms = [
			# executable
			str(self.exe),
		]

		if chunk_size:
			zip_prms.append(f"""-v{chunk_size}{'b' if isinstance(chunk_size, int) else ''}""")

		# param to create an archive
		zip_prms.append('a')

		if open_as:
			zip_prms.append(f'-t{open_as}')

		zip_prms.extend([
			# path to resulting archive
			str(output_loc),

			# archive params
			'-ssw',
		])

		# include paths
		if isinstance(input_data, list):
			for incl in input_data:
				zip_prms.append(str(incl))
		else:
			zip_prms.append(str(input_data))

		# exclude paths
		for excl in exclude:
			excl = excl.replace('/', '\\')
			zip_prms.append(f"""-xr!{excl}""")

		if not append_data:
			Path(output_loc).unlink(missing_ok=True)
			# compression parameters
			zip_prms.extend([
				# method. LZMA2, the coolset one
				'-m0=LZMA2',
				# Compression rate. 9 = max
				f'-mx={compression_rate}',
				# some sort of analysis which affects compression rate... 9 = max
				f'-myx={compression_rate}',
				# iteration passes, the more the better. 64 = 2 times more than default
				'-mmc=64',
				# Dict size. 12 MB
				'-md=12m',
				# word size. 273
				'-mfb=273',
				# solid block size. 2 GB
				'-ms=2g',
			])


		if echo == True:
			self.sp.run(zip_prms)
		else:
			self.sp.run(zip_prms, stdout=self.sp.DEVNULL)


	def unpack(self, input_archive, output_folder, extract_what=None, preserve_path=True):
		eprms = [
			str(self.exe),
			('e' if (extract_what and not preserve_path) else 'x'),
			'-o' + str(output_folder),
		]

		if isinstance(extract_what, list):
			eprms.extend([f'-i!{str(ew)}' for ew in extract_what])

		eprms.extend([
			str(input_archive),
			'-aoa',
		])

		# exec unpacking
		self.sp.run(eprms, stdout=self.sp.DEVNULL)


	def _list(self, input_archive):
		lparams = [
			str(self.exe),
			'-ba',
			'l',
			'-slt',
			str(input_archive),
		]

		with self.sp.Popen(lparams, stdout=self.sp.PIPE, bufsize=10**8) as pootis_pipe:
			pootis = pootis_pipe.stdout.read()

		# print('SEX', pootis)

