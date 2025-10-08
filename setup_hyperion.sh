#!/bin/bash
curl -sSL https://releases.hyperion-project.org/install | bash
sudo updateHyperionUser -u root
sudo raspi-config nonint do_spi 0
sudo reboot