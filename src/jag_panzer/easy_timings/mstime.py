

class perftest:
	def __init__(self, msg='Perftest: ', ms=True, as_return=False, log_lvl=1):
		import time, os
		self.time = time
		self.start = time.time()
		self.as_ms = True
		self.msg = msg
		self.as_return = as_return
		self.final = ''

		self.need_log_level = log_lvl
		self.env_log_level = int(os.environ['_jag-dev-lvl'])

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		mtime = (self.time.time() - self.start) * (1000 if self.as_ms else 1)
		if self.as_return:
			self.final = f'{self.msg} @@ {mtime}'
		else:
			if self.need_log_level == self.env_log_level and self.env_log_level != 0:
				print(self.msg, mtime)


















