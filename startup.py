import os

cmd_path = os.path.abspath(__file__)
parent_path = os.path.dirname(cmd_path)
grandparent_path = os.path.dirname(parent_path)

watch_dog_script = f"""
[Unit]

Description=Monitor Front Door

After=syslog.target
After=network-online.target

[Service]
Type=simple
ExecStart=watchdog -active-fps=6 -car-alart-secs=120 rtsp://admin:huang7758258@192.168.3.230
Restart=always

[Install]

WantedBy=network-online.target multi-user.target graphical.target

"""

service_file = "/lib/systemd/system/watchdog.service"
enable_cmd = f"""
sudo chmod 644 {service_file} &&
systemctl daemon-reload && 
systemctl enable watchdog.service &&
systemctl start watchdog.service
"""


def set_startup_run():
    # 设置开机自启动
    with open(service_file, "w+") as f:
        f.write(watch_dog_script)
    os.system(enable_cmd)


if __name__ == "__main__":
    set_startup_run()
