

class perftest:
	def __init__(self, msg='Perftest: ', ms=True, as_return=False):
		import time
		self.time = time
		self.start = time.time()
		self.as_ms = True
		self.msg = msg
		self.as_return = as_return
		self.final = ''

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		mtime = (self.time.time() - self.start) * (1000 if self.as_ms else 1)
		if self.as_return:
			self.final = f'{self.msg} @@ {mtime}'
		else:
			print(self.msg, mtime)
		

















