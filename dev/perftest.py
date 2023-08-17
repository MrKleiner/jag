import cProfile
import pstats

with cProfile.Profile() as pr:
	# WHATEVER NEEDS TO BE MEASURED GOES HERE
	pass

stats = pstats.Stats(pr)
stats.sort_stats(pstats.SortKey.TIME)
stats.print_stats()