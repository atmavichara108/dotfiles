from ranger.api.commands import Command
import os
import subprocess

class paste_as_root(Command):
	def execute(self):
		if self.fm.do_cut:
			self.fm.execute_console('shell sudo mv %c .')
		else:
			self.fm.execute_console('shell sudo cp -r %c .')

class fzf_select(Command):
    """
    :fzf_select

    Find a file using fzf.

    With a prefix argument select only directories.

    See: https://github.com/junegunn/fzf
    """
    def execute(self):
        import subprocess
        import os.path
        if self.quantifier:
            # match only directories
            command="find -L . \( -path '*/\.*' -o -fstype 'dev' -o -fstype 'proc' \) -prune \
            -o -type d -print 2> /dev/null | sed 1d | cut -b3- | fzf +m --reverse --header='Jump to file'"
        else:
            # match files and directories
            command="find -L . \( -path '*/\.*' -o -fstype 'dev' -o -fstype 'proc' \) -prune \
            -o -print 2> /dev/null | sed 1d | cut -b3- | fzf +m --reverse --header='Jump to filemap <C-f> fzf_select'"
        fzf = self.fm.execute_command(command, universal_newlines=True, stdout=subprocess.PIPE)
        stdout, stderr = fzf.communicate()
        if fzf.returncode == 0:
            fzf_file = os.path.abspath(stdout.rstrip('\n'))
            if os.path.isdir(fzf_file):
                self.fm.cd(fzf_file)
            else:
                self.fm.select_file(fzf_file)

class bgremove(Command):
    """
    :bgremove

    Удалить фон у текущего файла с помощью bgremove.
    Результат сохраняется рядом, с префиксом 'output_'.
    """

    def execute(self):
        fobj = self.fm.thisfile
        if not fobj or not fobj.path:
            self.fm.notify("Нет выбранного файла", bad=True)
            return

        src = fobj.path
        directory = os.path.dirname(src)
        basename = os.path.basename(src)
        out = os.path.join(directory, f"output_{basename}")

        cmd = f'bgremove -i "{src}" -o "{out}"'
        self.fm.notify(f"Запускаю: {cmd}")
        self.fm.run(cmd, flags='p')  # 'p' = показывать вывод в pager-е

class fzf_select(Command):
    """
    :fzf_select

    Найти файл/директорию через fzf с preview.
    """
    def execute(self):
        command = """
        fzf +m \
        --preview 'bat --style=numbers --color=always {} 2>/dev/null || eza --tree --level=2 --color=always {} 2>/dev/null' \
        --preview-window right:60%:wrap \
        --height 95% \
        --border
        """

        fzf = self.fm.execute_command(
            command,
            universal_newlines=True,
            stdout=subprocess.PIPE
        )
        stdout, _ = fzf.communicate()

        if fzf.returncode == 0:
            selected = os.path.abspath(stdout.rstrip('\n'))
            if os.path.isdir(selected):
                self.fm.cd(selected)
            else:
                self.fm.select_file(selected)

class fzf_rg(Command):
    """
    :fzf_rg [поисковый запрос]

    Поиск по содержимому файлов через ripgrep + fzf
    """
    def execute(self):
        if self.arg(1):
            query = self.rest(1)
        else:
            query = ""

        command = f"""
        rg --line-number --no-heading --color=always --smart-case '{query}' | \
        fzf --ansi \
        --delimiter : \
        --preview 'bat --color=always {{1}} --highlight-line {{2}}' \
        --preview-window '+{{2}}/2'
        """

        fzf = self.fm.execute_command(
            command,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            shell=True
        )
        stdout, _ = fzf.communicate()

        if fzf.returncode == 0:
            result = stdout.strip().split(':')
            if len(result) >= 2:
                filepath = result[0]
                self.fm.select_file(filepath)
