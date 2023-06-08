



class wtest:
	def __init__(self, smth, more):
		self.smth = smth
		self.more = more

	def __enter__(self):
		print('entering')
		return self

	def __exit__(self, type, value, traceback):
		print('exiting')

	def act_dance(self):
		print('Acting...', self.smth, self.more)


def proxy_attack(pootis):
	return wtest('AUTOMATIC', pootis)


with proxy_attack('MANUAL') as nen:
	nen.act_dance()