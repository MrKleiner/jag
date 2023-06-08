

def dict_pretty_print(d):
	sex = '\n'
	for key in d:
		sex += f"""{('>' + str(key) + '<').ljust(30)} :: >{str(d[key])}<""" + '\n'

	print(sex)

def multireplace(src, replace_pairs):
	for replace_what, replace_with in replace_pairs:
		src = src.replace(replace_what, replace_with)
	return src


def clamp(num, tgt_min, tgt_max):
	return max(tgt_min, min(num, tgt_max))