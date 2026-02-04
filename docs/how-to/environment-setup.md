# Environment Setup

> **Disclaimer:** This guide was generated with the help of Claude (Anthropic). While
> the steps below were accurate at the time of writing, your experience may differ
> depending on your operating system version, existing software, PATH configuration, or
> other environment-specific factors. If a step doesn't work as described, consult the
> official documentation linked in each section and search for your specific error
> message online — Stack Overflow, GitHub issues, and forums are great resources for
> troubleshooting environment-specific problems.

A step-by-step guide to setting up your development environment from scratch.
If you already have these tools installed, skip ahead to [Getting Started](getting-started.md).

---

## 1. Create a GitHub Account

GitHub is where this project's code is hosted. You'll need an account to clone the
repository and collaborate.

1. Go to [github.com](https://github.com)
2. Click **Sign up**
3. Enter your email, create a password, and choose a username
4. Complete the verification and click **Create account**

> **Tip:** Use your school email — GitHub offers free perks for students at
> [education.github.com](https://education.github.com).

---

## 2. Install Git

Git is the version-control tool that tracks changes to code.

### Windows

1. Download the installer from [git-scm.com/downloads/win](https://git-scm.com/downloads/win)
2. Run the installer — the default options are fine for most users
3. Open a **new** terminal (Command Prompt or PowerShell) and verify:

   ```
   git --version
   ```

### Mac

Git is bundled with the Xcode Command Line Tools. Open **Terminal** and run:

```
xcode-select --install
```

Follow the on-screen prompts. When it finishes, verify:

```
git --version
```

### Configure Git

After installing, tell Git who you are (use the email tied to your GitHub account):

```
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

---

## 3. Install VS Code

VS Code is a free code editor that works well for Python, Quarto, and Git.

### Windows

1. Download the installer from [code.visualstudio.com](https://code.visualstudio.com)
2. Run the installer
3. On the **Select Additional Tasks** page, check **Add to PATH** (usually checked by
   default)
4. Finish the installer and launch VS Code

### Mac

1. Download the `.zip` from [code.visualstudio.com](https://code.visualstudio.com)
2. Unzip it and drag **Visual Studio Code.app** into your **Applications** folder
3. Launch VS Code, then open the Command Palette (`Cmd+Shift+P`) and run
   **Shell Command: Install 'code' command in PATH**

### Recommended Extensions

Once VS Code is open, install these extensions (click the Extensions icon in the left
sidebar or press `Ctrl+Shift+X` / `Cmd+Shift+X`):

| Extension | What it does |
|---|---|
| **Python** (Microsoft) | Python language support, linting, debugging |
| **Quarto** (Quarto) | Syntax highlighting and preview for `.qmd` files |
| **GitHub Pull Requests** (GitHub) | Manage PRs and issues from inside VS Code |

---

## 4. Install Python

This project requires **Python 3.12 or newer**.

### Windows

1. Download the latest Python 3.12+ installer from [python.org/downloads](https://www.python.org/downloads/)
2. Run the installer
3. **Important:** Check the box **"Add python.exe to PATH"** on the first screen
4. Click **Install Now**
5. Open a **new** terminal and verify:

   ```
   python --version
   ```

### Mac

The recommended approach is to use the official installer:

1. Download the latest Python 3.12+ installer from [python.org/downloads](https://www.python.org/downloads/)
2. Run the `.pkg` installer and follow the prompts
3. Open a **new** Terminal and verify:

   ```
   python3 --version
   ```

> **Note:** On Mac the command is `python3`, not `python`. The tools used in this
> project (`uv`) handle this automatically, so you won't need to worry about it after
> this step.

---

## 5. Install uv

[uv](https://docs.astral.sh/uv/) is a fast Python package and project manager. This
project uses it to manage dependencies and run scripts.

### Windows

Open **PowerShell** and run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen your terminal, then verify:

```
uv --version
```

### Mac

Open **Terminal** and run:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen your terminal, then verify:

```
uv --version
```

---

## 6. Install Quarto

[Quarto](https://quarto.org) is used to create reports that mix text, code, and
visualizations.

### Windows

1. Download the installer from [quarto.org/docs/get-started](https://quarto.org/docs/get-started/)
2. Run the `.msi` installer and follow the prompts
3. Open a **new** terminal and verify:

   ```
   quarto --version
   ```

### Mac

1. Download the installer from [quarto.org/docs/get-started](https://quarto.org/docs/get-started/)
2. Run the `.pkg` installer and follow the prompts
3. Open a **new** terminal and verify:

   ```
   quarto --version
   ```

---

## Next Steps

Your environment is ready. Head over to the [Getting Started](getting-started.md) guide
to clone the project and install its dependencies.