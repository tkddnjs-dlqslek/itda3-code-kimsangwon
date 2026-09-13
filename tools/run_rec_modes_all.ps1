# ko 정책 -> merge 정책 순서로 gold 1,000장 재라벨. CPU 를 나눠 쓰지 않도록 순차 실행.
# Start-Process pwsh -ArgumentList '-NoProfile','-File','tools/run_rec_modes_all.ps1' `
#   -WorkingDirectory 'C:\Users\user\Desktop\ITDA 공모전\repo' -WindowStyle Hidden

$env:PYTHONIOENCODING = "utf-8"
$py = "C:/anaconda/envs/itda/python.exe"

& $py "tools/run_rec_mode.py" --mode ko --out "labels/auto_gold_v5_ko.csv" `
    1> "labels/rec_mode_ko.log" 2> "labels/rec_mode_ko.err"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $py "tools/run_rec_mode.py" --mode merge --out "labels/auto_gold_v5_merge.csv" `
    1> "labels/rec_mode_merge.log" 2> "labels/rec_mode_merge.err"

exit $LASTEXITCODE
