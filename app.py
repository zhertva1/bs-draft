import pygame
import os
import random

# Инициализация Pygame
pygame.init()

# Настройки экрана
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Brawl Stars Choice")

# Путь к папке с картинками
IMAGE_FOLDER = 'brawler_images'

# --- АВТОМАТИЧЕСКОЕ ПОЛУЧЕНИЕ СПИСКА БОЙЦОВ ---
if not os.path.exists(IMAGE_FOLDER):
    print(f"Ошибка: Папка '{IMAGE_FOLDER}' не найдена!")
    # Создаем пустой список, чтобы программа не вылетала
    brawlers_list = []
else:
    # Берем все файлы .png и убираем расширение
    brawlers_list = [f.replace('.png', '') for f in os.listdir(IMAGE_FOLDER) if f.endswith('.png')]

# Словарь для хранения загруженных картинок (чтобы не загружать их каждый кадр)
brawler_images = {}

def load_brawler_images():
    for name in brawlers_list:
        img_path = os.path.join(IMAGE_FOLDER, f"{name}.png")
        try:
            img = pygame.image.load(img_path).convert_alpha()
            # Масштабируем картинку, если нужно (например, 200x200)
            brawler_images[name] = pygame.transform.scale(img, (200, 200))
        except Exception as e:
            print(f"Не удалось загрузить {img_path}: {e}")

load_brawler_images()

# Проверка, что бойцы найдены
if not brawlers_list:
    print("В папке нет картинок бойцов!")
    selected_brawler = None
else:
    # Выбираем случайного бойца из списка названий файлов
    selected_brawler = random.choice(brawlers_list)
    print(f"Твой боец сегодня: {selected_brawler}")

# Основной цикл программы
running = True
while running:
    screen.fill((30, 30, 30)) # Темный фон
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        
        # Нажми ПРОБЕЛ, чтобы перевыбрать бойца
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE and brawlers_list:
                selected_brawler = random.choice(brawlers_list)

    # Отображение
    if selected_brawler:
        # Рисуем картинку
        image = brawler_images.get(selected_brawler)
        if image:
            screen.blit(image, (WIDTH//2 - 100, HEIGHT//2 - 150))
        
        # Рисуем текст (имя из названия файла)
        font = pygame.font.SysFont("Arial", 40)
        text_surface = font.render(selected_brawler.capitalize(), True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=(WIDTH//2, HEIGHT//2 + 100))
        screen.blit(text_surface, text_rect)

    pygame.display.flip()

pygame.quit()
