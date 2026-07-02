#!/usr/bin/env bash
export TERM=xterm-256color
cd /home/huangxb/pms
exec /usr/bin/ttyd -i 127.0.0.1 -p 7681 -W \
  -c "huangxb:YcoTDkL5pmAMe790rxMw" \
  -t titleFixed=PMS_Terminal -t "theme={\"background\":\"#1e1e1e\"}" \
  bash -lc "cd /home/huangxb/pms; exec screen -xRR cc"
