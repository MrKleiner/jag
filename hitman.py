import os

fuck = input('Service name: ')

os.system(f'systemctl stop {fuck}')
os.system(f'systemctl disable {fuck}')

os.system(f'rm /etc/systemd/system/{fuck}')
# and symlinks that might be related
os.system(f'rm /etc/systemd/system/{fuck}')

os.system(f'rm /usr/lib/systemd/system/{fuck}')
# and symlinks that might be related
os.system(f'rm /usr/lib/systemd/system/{fuck}')

os.system('systemctl daemon-reload')
os.system('systemctl reset-failed')