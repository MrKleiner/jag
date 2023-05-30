

def dict_pretty_print(d):
	sex = '\n'
	for key in d:
		sex += f"""{('>' + str(key) + '<').ljust(30)} :: >{str(d[key])}<""" + '\n'

	print(sex)



