from ranger.api.commands import Command
import os

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
