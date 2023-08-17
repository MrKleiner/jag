"""
Multiprocessing pool


with multiprocessing.Pool(3) as pool:
	print('pool')
	while True:
		pool.apply_async(base_room, (conn, address, sv_resources))
"""



"""
Get current IP (broken)


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _skt_get_ip:
	_skt_get_ip.connect(('8.8.8.8', 0))
	# _skt_get_ip.connect(('10.255.255.255', 1))
	current_ip = _skt_get_ip.getsockname()[0]
"""