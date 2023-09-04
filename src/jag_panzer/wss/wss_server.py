from pathlib import Path
import sys
# print('WSS Server path BEFORE tweaks:', *sys.path, sep='\n')
sys.path.append(str(Path(__file__).parent.parent))
# print('WSS Server path AFTER tweaks:', *sys.path, sep='\n')

from jag_util import JagConfigBase
import multiprocessing
import wss


def jag_wss_server_process(wss_resources):
	pass




class JagWssServerResources(JagConfigBase):
	"""
	Config for the WSS server.
	"""
	def __init__(self, init_config=None):
		self.create_base(
			{
				'port': None,

				'context': None,
			},
			init_config
		)

		# ------------------
		# Defaults
		# ------------------
		self.reg_cfg_group(
			'defaults',
			{
				# receive incoming messages as stream by default
				'recv_as_stream': False,

				# Max chunk size when streaming buffers
				'send_chunksize': 4096,

				# Max chunk size when receiving a message
				'recv_chunksize': 4096,

				# Max size of an incoming message
				'msg_max_size': (1024**2)*32,

				# Whether to mask the response messages or not
				'masked_response': False,
			}
		)



class JagWssServer(NestedProcessControl):
	"""
	Standard WSS server.
	"""
	def __init__(self, launch_params=None):
		self.server_params = JagWssServerResources(launch_params)

	def launch(self):
		self.server_process = multiprocessing.Process(target=jag_wss_server_process, args=(self.server_params,))
		self.server_process.start()
		self.running = True

	def create_session(self, cl_con):
		return wss_session(cl_con)









