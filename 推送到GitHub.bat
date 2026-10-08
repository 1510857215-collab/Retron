@echo off
chcp 936 >nul
title 推送 Retron 到 GitHub
cd /d "%~dp0"

echo.
echo  ================================================
echo    推送 Retron 源代码到 GitHub
echo  ================================================
echo.
echo    请先在 GitHub 网页上建好一个【空】仓库
echo    （建的时候三个勾选框都不要勾）
echo.

set "REPO=%~1"
if not "%REPO%"=="" goto haveRepo

echo    把仓库地址粘贴进来（在窗口里点右键即可粘贴），回车
echo    形如： https://github.com/你的用户名/Retron.git
echo.
set /p REPO=  仓库地址: 

:haveRepo
if "%REPO%"=="" goto empty

echo.
echo  [1/3] 写入仓库地址……
git remote remove origin >nul 2>nul
git remote add origin "%REPO%"
if errorlevel 1 goto failed
echo        完成

echo  [2/3] 检查网络代理……
netstat -an | findstr ":7890" | findstr "LISTENING" >nul
if errorlevel 1 goto noProxy
git config http.proxy http://127.0.0.1:7890 >nul 2>nul
git config https.proxy http://127.0.0.1:7890 >nul 2>nul
echo        检测到本机代理，已启用
goto push

:noProxy
echo        未检测到代理，直连推送

:push
echo  [3/3] 正在推送，请稍候（约 80 MB）……
echo.
git push -u origin main
if errorlevel 1 goto failed

echo.
echo  ================================================
echo    推送成功！可以到 GitHub 网页上刷新看看了
echo  ================================================
echo.
pause
exit /b 0

:empty
echo.
echo    没有输入地址，已取消。
pause
exit /b 1

:failed
echo.
echo    出问题了。请把上面的提示内容截图留档。
echo.
echo    小提示：如果提示 rejected / failed to push，
echo    多半是建仓库时勾了 README —— 删掉线上仓库重建一个空仓库即可。
echo.
pause
exit /b 1
