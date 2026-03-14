!/bin/bash
rm msieve.fb
rm msieve.dat
rm msieve.dat.cyc
echo "$1" > worktodo.ini
timeout "$2s" bash -c "./msieve  -v -np -t 32 sortlib=cub/sort_engine.so polydegree=5 gpu_mem_mb=32000 stage1_norm=2e25 stage2_norm=1e20 min_evalue=1e-15 min_coeff=3e5 max_coeff=5e6 -g 0"

# 입력 파일 및 출력 파일 설정
MSIEVE_FB_FILE="msieve.fb"
CADO_POLY_FILE="cado.poly"

# fb 파일이 존재하는지 확인
if [ ! -f "$MSIEVE_FB_FILE" ]; then
    echo "Error: Msieve fb file ($MSIEVE_FB_FILE) not found!"
    exit 1
fi

# fb 파일에서 필요한 정보 추출
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

# 필수 값이 존재하는지 확인
if [ -z "$N_VALUE" ] || [ -z "$SKEW_VALUE" ] || [ -z "$Y0_VALUE" ] || [ -z "$Y1_VALUE" ] || [ -z "$C0_VALUE" ] || [ -z "$C5_VALUE" ]; then
    echo "Error: Missing required values in $MSIEVE_FB_FILE"
    exit 1
fi

# poly 파일 생성
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

echo "# MurphyE (Bf=2.684e+08,Bg=1.342e+08,area=8.053e+13) = 1.621e-07" >> "$CADO_POLY_FILE"
echo "# f(x) = $C5_VALUE*x^5 + $C4_VALUE*x^4 + $C3_VALUE*x^3 + $C2_VALUE*x^2 + $C1_VALUE*x + $C0_VALUE" >> "$CADO_POLY_FILE"
echo "# g(x) = $Y1_VALUE*x + $Y0_VALUE" >> "$CADO_POLY_FILE"

echo "Converted $MSIEVE_FB_FILE to $CADO_POLY_FILE successfully."
