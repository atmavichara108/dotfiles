#!/bin/bash
IFACE="enp0s31f6"

BROTHER_IP="192.168.0.15"

# Сброс старых правил
sudo tc qdisc del dev $IFACE root 2>/dev/null

# Создаём HTB (1000 Мбит/с — скорость канала)
sudo tc qdisc add dev $IFACE root handle 1: htb default 30

# Корневой класс (весь канал)
sudo tc class add dev $IFACE parent 1: classid 1:1 htb rate 1000mbit

# Твой трафик: гарантия 300, макс 1000, приоритет 1 (высший)
sudo tc class add dev $IFACE parent 1:1 classid 1:10 htb rate 300mbit ceil 1000mbit prio 1

# Брат: гарантия 300, макс 700, приоритет 2
sudo tc class add dev $IFACE parent 1:1 classid 1:20 htb rate 300mbit ceil 700mbit prio 2

# Остальные устройства: гарантия 100, макс 500, приоритет 3
sudo tc class add dev $IFACE parent 1:1 classid 1:30 htb rate 100mbit ceil 500mbit prio 3

# Фильтры (направляем трафик брата в класс 1:20)
sudo tc filter add dev $IFACE protocol ip parent 1:0 prio 2 u32 match ip dst $BROTHER_IP flowid 1:20

# Твой трафик — класс 1:10 (default уже стоит, но можно явно)
sudo tc filter add dev $IFACE protocol ip parent 1:0 prio 1 u32 match ip src 192.168.0.59/32 flowid 1:10

echo "QoS настроен. Твой класс: 1:10, Брат: 1:20"
