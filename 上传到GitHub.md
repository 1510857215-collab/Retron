把 Retron 的源代码上传到 GitHub —— 三步走
================================================

源代码已经打包整理好了，位置在：
    C:\Users\zzl\Desktop\Retron-Source

它是一个已经准备好的本地仓库（已经做好第一次提交），你只需要：
    ① 在 GitHub 网页上建一个空项目
    ② 把地址填进来
    ③ 点一下推送

下面每一步都有具体操作。


────────────────────────────────────────────
第 ① 步：在 GitHub 上建一个空项目
────────────────────────────────────────────

1. 浏览器打开 https://github.com ，登录你的账号

2. 右上角「+」→「New repository」

3. 填写：
   · Repository name（项目名）：  Retron
   · Description（描述，可空）：  完全离线的有机合成工作台
   · 选 Public（公开）或 Private（私有），都可以
   · ⚠️ 下面三个勾选框【一个都不要勾】
     （不要勾 Add a README file / .gitignore / license —— 因为本地已经有了，
       勾了会导致推送冲突）

4. 点绿色按钮「Create repository」

5. 建好后页面会显示一段命令，你只需要记下仓库地址，形如：
       https://github.com/你的用户名/Retron.git


────────────────────────────────────────────
第 ② 步：把地址填进本地仓库
────────────────────────────────────────────

方法 A（推荐，双击就行）：
    双击桌面 → Retron-Source 文件夹里的  推送到GitHub.bat
    按提示粘贴上面的仓库地址，回车即可。

方法 B（手动敲命令）：
    在 Retron-Source 文件夹里空白处右键 →「Open Git Bash here」，依次输入：

        git remote add origin https://github.com/你的用户名/Retron.git
        git push -u origin main

    第一次推送会弹窗要求登录 GitHub，按提示授权即可。


────────────────────────────────────────────
第 ③ 步（可选）：把提交者名字改成你自己
────────────────────────────────────────────

本地仓库目前用的是默认名字（Retron / retron@local）。
如果你想让它显示成你自己的 GitHub 身份，在推送【之前】执行：

    git config user.name "你的名字"
    git config user.email "你的GitHub注册邮箱"
    git commit --amend --reset-author --no-edit

然后再推送。已经推送过也没关系，改完重新推送即可。


────────────────────────────────────────────
常见问题
────────────────────────────────────────────

Q：提示 "remote origin already exists"？
A：说明已经加过地址了。想换地址就先执行：
       git remote set-url origin 新地址

Q：提示 "failed to push some refs" / "rejected"？
A：多半是建仓库时勾了 README。执行下面这条再推：
       git pull --rebase origin main
   或者干脆删掉 GitHub 上的仓库，重新建一个（记得别勾任何选项）。

Q：推送很慢或中断？
A：仓库约 80 MB，国内直连 GitHub 有时不稳。挂上代理（Clash）后重试：
       git config --global http.proxy http://127.0.0.1:7890
       git config --global https.proxy http://127.0.0.1:7890
   推送完可以取消代理：
       git config --global --unset http.proxy
       git config --global --unset https.proxy

Q：模型和运行环境要不要也传上去？
A：不用，也不建议。仓库里只放源代码（80 MB）。
   模型和词典来自公开来源，README 里写了各自的出处；
   完整的可运行版本（约 11 GB）靠文件夹拷贝分发，不走 GitHub。


────────────────────────────────────────────
仓库里都有什么（145 个文件）
────────────────────────────────────────────

    app/            本地服务程序
    engine/         五个引擎的源码
    web/            界面、画板（含汉化后的 Ketcher 构建产物）
    shell/          Electron 桌面外壳
    tools/          维护脚本 + 五套环境的依赖清单
      ├─ repair_env.py           换电脑后自动修环境路径
      ├─ check_runtime_deps.py   运行环境依赖体检
      ├─ make_dist.py            生成可分发版本
      ├─ requirements/           五套环境各自的依赖清单
      └─ archived-scripts/       开发期测试脚本（画板汉化、端到端验证等）
    README.md       项目介绍（GitHub 首页会显示它）
    LICENSE         MIT 许可证 + 第三方组件声明
    .gitignore      已排除模型、环境、缓存等大文件
    使用说明.md     给使用者的功能说明
    首次使用必读.txt 安装 / 换电脑 / 排错
    蓝图.md         技术设计文档
