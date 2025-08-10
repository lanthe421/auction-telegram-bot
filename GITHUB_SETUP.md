# 🚀 Настройка GitHub репозитория

## 📋 Пошаговая инструкция

### 1. Создание репозитория на GitHub

1. Перейдите на [GitHub.com](https://github.com) и войдите в аккаунт
2. Нажмите кнопку **"New"** или **"+"** в правом верхнем углу
3. Выберите **"New repository"**
4. Заполните форму:
   - **Repository name**: `auction-telegram-bot` (или другое название)
   - **Description**: `Полнофункциональный аукционный бот для Telegram с веб-панелью управления`
   - **Visibility**: Public или Private (по вашему выбору)
   - **НЕ ставьте галочки** на "Add a README file", "Add .gitignore", "Choose a license"
5. Нажмите **"Create repository"**

### 2. Подключение локального репозитория

После создания репозитория, выполните эти команды в терминале:

```bash
# Замените YOUR_USERNAME на ваше имя пользователя GitHub
# Замените REPO_NAME на название вашего репозитория

git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git
git branch -M main
git push -u origin main
```

### 3. Пример команд

Если ваш репозиторий называется `auction-telegram-bot` и ваш username `john_doe`:

```bash
git remote add origin https://github.com/john_doe/auction-telegram-bot.git
git branch -M main
git push -u origin main
```

### 4. Проверка результата

После выполнения команд:
1. Обновите страницу GitHub репозитория
2. Вы должны увидеть все файлы проекта
3. README.md будет отображаться на главной странице

## 🔧 Дополнительные настройки

### Настройка GitHub Pages (опционально)

Если хотите создать сайт документации:

1. Перейдите в **Settings** репозитория
2. Прокрутите до раздела **"Pages"**
3. В **"Source"** выберите **"Deploy from a branch"**
4. Выберите ветку **"main"** и папку **"/ (root)"**
5. Нажмите **"Save"**

### Настройка Issues и Projects

1. **Issues**: Включены по умолчанию, можно использовать для баг-репортов
2. **Projects**: Можно создать для управления задачами
3. **Wiki**: Можно включить для дополнительной документации

## 📝 Что дальше?

После загрузки проекта на GitHub:

1. **Обновите README.md** - замените `your-username` на ваше реальное имя пользователя
2. **Добавьте теги** (tags) для версий: `git tag v1.0.0 && git push origin v1.0.0`
3. **Создайте Issues** для планирования новых функций
4. **Настройте Actions** для автоматического тестирования (опционально)

## 🆘 Если что-то пошло не так

### Ошибка аутентификации:
```bash
# Настройте токен доступа или используйте SSH
git remote set-url origin https://YOUR_TOKEN@github.com/YOUR_USERNAME/REPO_NAME.git
```

### Ошибка push:
```bash
# Если репозиторий уже существует на GitHub
git pull origin main --allow-unrelated-histories
git push -u origin main
```

### Изменение URL репозитория:
```bash
git remote set-url origin https://github.com/NEW_USERNAME/NEW_REPO_NAME.git
```

---

🎉 **Поздравляем! Ваш проект теперь на GitHub!** 