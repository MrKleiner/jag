








def main(request, response, services):
	Path = request.srv_res.pylib.Path

	if request.relative_to()




if __name__ == '__main__':
	from panzer.server import server_process

	server_process({
		'doc_root': r'E:\!webdesign\jag',
		'port': 56817,
		'room_file': __file__,
		'dir_listing': {
			'enabled': True,
		}
	})