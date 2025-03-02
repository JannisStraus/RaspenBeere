# Install
sudo apt update && sudo apt upgrade -y
curl -sSL https://install.pi-hole.net | bash

# Start / Stop
sudo systemctl start pihole-FTL
sudo systemctl stop pihole-FTL
