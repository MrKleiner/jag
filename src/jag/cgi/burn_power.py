import os, socket, shutil
from pathlib import Path

def clear():
	os.system('cls' if os.name == 'nt' else 'clear')

def is_port_in_use(port):
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
		return s.connect_ex(('localhost', port)) != 0

def dict_replace(src, matches):
	for drp in matches:
		src = src.replace(drp, matches[drp])
	return src

thisdir = Path(__file__).parent

class ez_service:
	def __init__(self):
		self.prmdict = {
			'docroot': None,
			'service_name': None,
			'run_user': None,
			'port': None,
			'pypath': None,
			'cfgloc': None,
		}

		self.msg = ''

		clear()
		self.mainl()

	def print_stats(self):
		clear()
		print('')
		for idx, stat in enumerate(self.prmdict):
			if self.prmdict[stat]:
				print(f'{idx+1} - {stat.ljust(20)}:', self.prmdict[stat])

		print(self.msg)


	def mainl(self):
		self._docroot()
		self.msg = ''
		self._service_name()
		self.msg = ''
		self._run_user()
		self.msg = ''
		self._port()
		self.msg = ''
		self._pypath()
		self.msg = ''
		self._cfgloc()
		self.msg = ''

		while True:
			self.print_stats()
			print('Is the above info correct?')
			print('If you want to tweak something - press a number')
			print('If you are happy - type "y"')
			decide = input('Your answer: ')
			if decide == 'y':
				break

			decide_dict = {
				'1': self._docroot,
				'2': self._service_name,
				'3': self._run_user,
				'4': self._port,
				'5': self._cfgloc,
			}

			if not decide in decide_dict:
				continue

			decide_dict[decide]()



	def _service_name(self):
		while True:
			service_name = input('Enter service name: ')
			if not service_name.strip():
				self.print_stats()
				self.msg = 'Invalid service name'
				continue
			break

		self.prmdict['service_name'] = service_name

	def _run_user(self):
		while True:
			self.print_stats()
			run_user = input('User to run as ("-" for www-data): ')
			if not run_user.strip():
				self.msg = 'Invalid username'
				continue

			if run_user.strip() == '-':
				run_user = 'www-data'
				break
			break

		self.prmdict['run_user'] = run_user

	def _port(self):
		while True:
			self.print_stats()
			port = input('Port: ')
			try:
				port = int(port)
				is_port_in_use(port)
			except Exception as e:
				self.msg = 'Invalid port'
				continue
			break

		self.prmdict['port'] = port

	def _docroot(self):
		while True:
			self.print_stats()
			docroot = input('Document Root: ')
			if not Path(docroot.strip('"')).is_dir() or not docroot.strip('"'):
				self.msg = 'Invalid directory'
				continue
			break

		self.prmdict['docroot'] = docroot.strip()

	def _cfgloc(self):
		while True:
			self.print_stats()
			cfgloc = input('Config Location (create new folder named after the service there): ')
			if not Path(cfgloc.strip('"')).is_dir() or not cfgloc.strip('"'):
				self.msg = 'Invalid directory'
				continue
			break

		self.prmdict['cfgloc'] = cfgloc.strip()

	def _pypath(self):
		while True:
			self.print_stats()
			pypath = input('Path to python executable (/usr/bin/python3): ')
			if not Path(pypath.strip('"')).is_file(): 
				self.msg = 'Invalid path'
				continue
			break

		self.prmdict['pypath'] = pypath.strip()




if __name__ == '__main__':
	fuckoff = ez_service()

	unit_match = {
		'$JAG_SERVICENAME$': fuckoff.prmdict['service_name'],
		'$JAG_CFGLOC$': str(Path(fuckoff.prmdict['cfgloc']) / fuckoff.prmdict['service_name']).rstrip('/'),
	}
	unit = dict_replace((thisdir / 'templates' / 'unit.service').read_text(), unit_match)

	Path(f"""/etc/systemd/system/{fuckoff.prmdict['service_name']}.service""").write_text(unit)

	cfgdir = Path(fuckoff.prmdict['cfgloc'])
	cfgdir.mkdir(exist_ok=True)
	cfgdir = cfgdir / fuckoff.prmdict['service_name']
	cfgdir.mkdir(exist_ok=True)
	(cfgdir / 'conf-enabled').mkdir(exist_ok=True)

	basecfg_match = {
		'$JAG_DOCROOT$':         fuckoff.prmdict['docroot'].rstrip('/'),
		'$JAG_PIDFILE$':         str(Path('/run') / f"""{fuckoff.prmdict['service_name']}.pid""").rstrip('/'),
		'$JAG_USERNAME$':        fuckoff.prmdict['run_user'],
		'$JAG_PORTNUM$':         str(fuckoff.prmdict['port']),
		'$JAG_INCLUDE_CFG_DIR$': str(Path(cfgdir) / 'conf-enabled').rstrip('/'),
	}
	basecfg = dict_replace((thisdir / 'templates' / 'light_httpd' / 'server_prms.conf').read_text(), basecfg_match)
	(cfgdir / 'server_prms.conf').write_text(basecfg)

	cgicfg_match = {
		'$JAG_PYPATH$': fuckoff.prmdict['pypath'].rstrip('/'),
	}
	basecfg = dict_replace((thisdir / 'templates' / 'light_httpd' / 'conf-enabled' / '10-cgi.conf').read_text(), cgicfg_match)
	(cfgdir / 'conf-enabled' / '10-cgi.conf').write_text(basecfg)

	shutil.copy(
		thisdir / 'templates' / 'light_httpd' / 'conf-enabled' / '10-status.conf',
		cfgdir / 'conf-enabled' / '10-status.conf'
	)
	shutil.copy(
		thisdir / 'templates' / 'light_httpd' / 'conf-enabled' / '10-accesslog.conf',
		cfgdir / 'conf-enabled' / '10-accesslog.conf'
	)

	os.system('systemctl daemon-reload')
	os.system(f"""systemctl enable {fuckoff.prmdict['service_name']}""")
	os.system(f"""service {fuckoff.prmdict['service_name']} start""")
	print('')
	print('Done')
	print('')




