#!/bin/bash
set -euo pipefail

rm -f msieve.fb msieve.dat msieve.dat.cyc
echo "$1" > worktodo.ini

N_INPUT="$1"
TIMEOUT_SEC="$2"

# decimal 정수의 bit length 계산
BITS=$(python3 -c "print(int('$N_INPUT').bit_length())")

# 기본값
THREADS=32
POLYDEGREE=5
GPU_MEM_MB=32000
GPU_ID=0

STAGE1_NORM=""
STAGE2_NORM=""
MIN_EVALUE=""
MIN_COEFF=""
MAX_COEFF=""

# 300~480 비트 구간별 시작 파라미터
if   [ "$BITS" -le 309 ]; then
    STAGE1_NORM="8e21"
    STAGE2_NORM="5e16"
    MIN_EVALUE="1e-13"
    MIN_COEFF="4e4"
    MAX_COEFF="6e5"

elif [ "$BITS" -le 319 ]; then
    STAGE1_NORM="2e22"
    STAGE2_NORM="1e17"
    MIN_EVALUE="7e-14"
    MIN_COEFF="5e4"
    MAX_COEFF="8e5"

elif [ "$BITS" -le 329 ]; then
    STAGE1_NORM="5e22"
    STAGE2_NORM="3e17"
    MIN_EVALUE="5e-14"
    MIN_COEFF="7e4"
    MAX_COEFF="1.0e6"

elif [ "$BITS" -le 339 ]; then
    STAGE1_NORM="1e23"
    STAGE2_NORM="8e17"
    MIN_EVALUE="3e-14"
    MIN_COEFF="9e4"
    MAX_COEFF="1.3e6"

elif [ "$BITS" -le 349 ]; then
    STAGE1_NORM="2e23"
    STAGE2_NORM="2e18"
    MIN_EVALUE="2e-14"
    MIN_COEFF="1.2e5"
    MAX_COEFF="1.6e6"

elif [ "$BITS" -le 359 ]; then
    STAGE1_NORM="4e23"
    STAGE2_NORM="5e18"
    MIN_EVALUE="1e-14"
    MIN_COEFF="1.5e5"
    MAX_COEFF="2.0e6"

elif [ "$BITS" -le 369 ]; then
    STAGE1_NORM="8e23"
    STAGE2_NORM="1e19"
    MIN_EVALUE="8e-15"
    MIN_COEFF="1.8e5"
    MAX_COEFF="2.4e6"

elif [ "$BITS" -le 379 ]; then
    STAGE1_NORM="1.5e24"
    STAGE2_NORM="2e19"
    MIN_EVALUE="5e-15"
    MIN_COEFF="2.0e5"
    MAX_COEFF="2.8e6"

elif [ "$BITS" -le 389 ]; then
    STAGE1_NORM="3e24"
    STAGE2_NORM="4e19"
    MIN_EVALUE="3e-15"
    MIN_COEFF="2.2e5"
    MAX_COEFF="3.2e6"

elif [ "$BITS" -le 399 ]; then
    STAGE1_NORM="5e24"
    STAGE2_NORM="6e19"
    MIN_EVALUE="2e-15"
    MIN_COEFF="2.4e5"
    MAX_COEFF="3.6e6"

elif [ "$BITS" -le 409 ]; then
    STAGE1_NORM="7e24"
    STAGE2_NORM="8e19"
    MIN_EVALUE="1.5e-15"
    MIN_COEFF="2.6e5"
    MAX_COEFF="4.0e6"

elif [ "$BITS" -le 419 ]; then
    STAGE1_NORM="1e25"
    STAGE2_NORM="1e20"
    MIN_EVALUE="1e-15"
    MIN_COEFF="2.8e5"
    MAX_COEFF="4.3e6"

elif [ "$BITS" -le 429 ]; then
    STAGE1_NORM="1.2e25"
    STAGE2_NORM="1.1e20"
    MIN_EVALUE="1e-15"
    MIN_COEFF="3.0e5"
    MAX_COEFF="4.6e6"

elif [ "$BITS" -le 439 ]; then
    STAGE1_NORM="1.5e25"
    STAGE2_NORM="1.2e20"
    MIN_EVALUE="1e-15"
    MIN_COEFF="3.0e5"
    MAX_COEFF="4.8e6"

elif [ "$BITS" -le 449 ]; then
    STAGE1_NORM="1.8e25"
    STAGE2_NORM="1.3e20"
    MIN_EVALUE="1e-15"
    MIN_COEFF="3.0e5"
    MAX_COEFF="5.0e6"

elif [ "$BITS" -le 459 ]; then
    STAGE1_NORM="2e25"
    STAGE2_NORM="1e20"
    MIN_EVALUE="1e-15"
    MIN_COEFF="3e5"
    MAX_COEFF="5e6"

elif [ "$BITS" -le 469 ]; then
    STAGE1_NORM="2.3e25"
    STAGE2_NORM="1.2e20"
    MIN_EVALUE="8e-16"
    MIN_COEFF="3.5e5"
    MAX_COEFF="6.0e6"

elif [ "$BITS" -le 479 ]; then
    STAGE1_NORM="2.7e25"
    STAGE2_NORM="1.5e20"
    MIN_EVALUE="7e-16"
    MIN_COEFF="4.0e5"
    MAX_COEFF="7.0e6"

else
    STAGE1_NORM="3e25"
    STAGE2_NORM="2e20"
    MIN_EVALUE="5e-16"
    MIN_COEFF="5e5"
    MAX_COEFF="8e6"
fi

echo "[INFO] N bits                : $BITS"
echo "[INFO] polydegree           : $POLYDEGREE"
echo "[INFO] gpu_mem_mb           : $GPU_MEM_MB"
echo "[INFO] stage1_norm          : $STAGE1_NORM"
echo "[INFO] stage2_norm          : $STAGE2_NORM"
echo "[INFO] min_evalue           : $MIN_EVALUE"
echo "[INFO] min_coeff            : $MIN_COEFF"
echo "[INFO] max_coeff            : $MAX_COEFF"

timeout "${TIMEOUT_SEC}s" bash -c "./msieve \
  -v -np -t ${THREADS} \
  sortlib=cub/sort_engine.so \
  polydegree=${POLYDEGREE} \
  gpu_mem_mb=${GPU_MEM_MB} \
  stage1_norm=${STAGE1_NORM} \
  stage2_norm=${STAGE2_NORM} \
  min_evalue=${MIN_EVALUE} \
  min_coeff=${MIN_COEFF} \
  max_coeff=${MAX_COEFF} \
  -g ${GPU_ID}"

# 입력 파일 및 출력 파일 설정
MSIEVE_FB_FILE="msieve.fb"
CADO_POLY_FILE="cado.poly"

if [ ! -f "$MSIEVE_FB_FILE" ]; then
    echo "Error: Msieve fb file ($MSIEVE_FB_FILE) not found!"
    exit 1
fi

N_VALUE=$(grep "^N " "$MSIEVE_FB_FILE" | awk '{print $2}')
SKEW_VALUE=$(grep "^SKEW " "$MSIEVE_FB_FILE" | awk '{print $2}')
Y0_VALUE=$(grep "^R0 " "$MSIEVE_FB_FILE" | awk '{print $2}')
Y1_VALUE=$(grep "^R1 " "$MSIEVE_FB_FILE" | awk '{print $2}')
C0_VALUE=$(grep "^A0 " "$MSIEVE_FB_FILE" | awk '{print $2}')
C1_VALUE=$(grep "^A1 " "$MSIEVE_FB_FILE" | awk '{print $2}')
C2_VALUE=$(grep "^A2 " "$MSIEVE_FB_FILE" | awk '{print $2}')
C3_VALUE=$(grep "^A3 " "$MSIEVE_FB_FILE" | awk '{print $2}')
C4_VALUE=$(grep "^A4 " "$MSIEVE_FB_FILE" | awk '{print $2}')
C5_VALUE=$(grep "^A5 " "$MSIEVE_FB_FILE" | awk '{print $2}')

if [ -z "$N_VALUE" ] || [ -z "$SKEW_VALUE" ] || [ -z "$Y0_VALUE" ] || [ -z "$Y1_VALUE" ] || [ -z "$C0_VALUE" ] || [ -z "$C5_VALUE" ]; then
    echo "Error: Missing required values in $MSIEVE_FB_FILE"
    exit 1
fi

echo "n: $N_VALUE" > "$CADO_POLY_FILE"
echo "skew: $SKEW_VALUE" >> "$CADO_POLY_FILE"
echo "c0: $C0_VALUE" >> "$CADO_POLY_FILE"
echo "c1: $C1_VALUE" >> "$CADO_POLY_FILE"
echo "c2: $C2_VALUE" >> "$CADO_POLY_FILE"
echo "c3: $C3_VALUE" >> "$CADO_POLY_FILE"
echo "c4: $C4_VALUE" >> "$CADO_POLY_FILE"
echo "c5: $C5_VALUE" >> "$CADO_POLY_FILE"
echo "Y0: $Y0_VALUE" >> "$CADO_POLY_FILE"
echo "Y1: $Y1_VALUE" >> "$CADO_POLY_FILE"

echo "# f(x) = $C5_VALUE*x^5 + $C4_VALUE*x^4 + $C3_VALUE*x^3 + $C2_VALUE*x^2 + $C1_VALUE*x + $C0_VALUE" >> "$CADO_POLY_FILE"
echo "# g(x) = $Y1_VALUE*x + $Y0_VALUE" >> "$CADO_POLY_FILE"

echo "Converted $MSIEVE_FB_FILE to $CADO_POLY_FILE successfully."