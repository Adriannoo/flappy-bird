# Build para Windows 64 bits

O jogador não precisa de Python. Estas ferramentas são necessárias apenas para gerar os arquivos de distribuição.

## Preparar

Use Python 3.12 de 64 bits e o ambiente `.venv` do projeto. Na raiz:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

## Gerar o executável

```powershell
.\.venv\Scripts\python.exe build.py
```

Resultado: `dist/FlappyBird.exe`, contendo o Python, Pygame, imagens, fontes e sons.

## Gerar o instalador

Instale o Inno Setup 6 ou 7. Se estiver no local padrão do Windows ou no PATH:

```powershell
.\.venv\Scripts\python.exe build.py --installer
```

Para uma instalação em outra pasta, informe o compilador:

```powershell
.\.venv\Scripts\python.exe build.py --installer --iscc "C:\caminho\Inno Setup\ISCC.exe"
```

Resultado: `releases/FlappyBird-Setup.exe`, dentro do projeto. Instala para o usuário atual, cria atalho no menu Iniciar, oferece atalho na área de trabalho e inclui desinstalador.

O instalador pronto já está em `releases/`: execute-o para instalar o jogo sem Python. As próximas gerações com `build.py --installer` atualizam esse mesmo arquivo. A pasta `releases/` não está no `.gitignore`; `build/` e `dist/` guardam os arquivos gerados durante a compilação.

Recorde e histórico ficam em `%LOCALAPPDATA%\AdrianoGames\FlappyBird\profile.json`, separados dos arquivos instalados. A desinstalação preserva esses dados. O recorde antigo em `data/record.json` é aproveitado ao executar o código-fonte quando ainda não há perfil na nova localização.

Volume, som e tela cheia são salvos em `settings.json`, na mesma pasta de dados. O menu **Configurações** permite ajustá-los; `M` alterna o som e `F11` alterna a tela cheia. Ao mudar a tela durante uma partida, o jogo pausa.

O início e a retomada têm contagem de três segundos, sem avançar a partida. As medalhas são bronze aos 10 pontos, prata aos 25, ouro aos 50 e platina aos 100. O resumo do histórico considera as últimas 20 partidas registradas, incluindo as interrompidas.

## Conferir o pacote

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\dist\FlappyBird.exe --check-build "$env:TEMP\flappy-check"
```

O modo de conferência não abre janela e usa somente a pasta indicada para dados e capturas. Verifique `result.json`: `ok` deve ser `true`.

Use uma pasta nova de conferência a cada teste. Para diagnosticar a distribuição em pasta antes do arquivo único, use `build.py --onedir`. Não distribua os arquivos de `build/`.

O alvo deste build é Windows 10/11 de 64 bits. Builds de outros sistemas operacionais precisam ser gerados e verificados separadamente.
