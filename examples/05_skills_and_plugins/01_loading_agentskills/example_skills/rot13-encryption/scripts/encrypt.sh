#!/bin/bash
# ROT13 加密 - 加密/解密输入消息
echo "$1" | tr 'A-Za-z' 'N-ZA-Mn-za-m'
