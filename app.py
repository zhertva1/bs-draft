import pygame
import os
import random

# Инициализация
pygame.init()

# Настройки окна
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Brawler Draft")

# Папка с картинками
IMAGE_FOLDER = 'brawler_images'

# --- ПОЛУЧЕНИЕ ИМЕН ИЗ ПАПКИ ---
if not os.path.exists(IMAGE_FOLDER):
    print(f"Папка '{IMAGE_FOLDER}' не найдена!")
    brawlers_list = []
else:
    brawlers_list = [f.replace('.png', '') for f in os.listdir(IMAGE_FOLDER) if f.endswith('.png')]

# Загрузка картинок
brawler_images = {}
def load_all_images():
    for name in brawlers_list:
        path = os.path.join(IMAGE_FOLDER, f"{name}.png")
        try:
            img = pygame.image.load(path).convert_alpha()
            brawler_images[name] = pygame.transform.scale(img, (250, 250))
        except:
            pass

load_all_images()

# Переменная для текущего выбора
selected_brawler = None

# Шрифты
font_name = pygame.font.SysFont("Arial", 40, bold=True)
font_button = pygame.font.SysFont("Arial", 25, bold=True)

# Параметры кнопки сброса
reset_button_rect = pygame.Rect(WIDTH // 2 - 150, HEIGHT - 70, 300, 50)
BUTTON_COLOR = (200, 50, 50)      # Красный
BUTTON_HOVER_COLOR = (255, 70, 70) # Светло-красный

running = True
while running:
    mouse_pos = pygame.mouse.get_pos()
    screen.fill((20, 20, 40)) # Фон
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        
        # Выбор нового бойца на Пробел
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE and brawlers_list:
                selected_brawler = random.choice(brawlers_list)
        
        # Проверка клика по кнопке сброса
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: # Левая кнопка мыши
                if reset_button_rect.collidepoint(event.pos):
                    selected_brawler = None # СБРОС

    # --- ОТОБРАЖЕНИЕ БОЙЦА ---
    if selected_brawler:
        # Картинка
        img = brawler_images.get(selected_brawler)
        if img:
            rect = img.get_rect(center=(WIDTH//2, HEIGHT//2 - 50))
            screen.blit(img, rect)
        
        # Имя
        name_text = font_name.render(selected_brawler.upper(), True, (255, 255, 255))
        name_rect = name_text.get_rect(center=(WIDTH//2, HEIGHT//2 + 150))
        screen.blit(name_text, name_rect)
    else:
        # Текст, если ничего не выбрано
        empty_text = font_button.render("Нажми ПРОБЕЛ, чтобы начать драфт", True, (100, 100, 150))
        screen.blit(empty_text, (WIDTH//2 - 180, HEIGHT//2 - 20))

    # --- РИСУЕМ КНОПКУ СБРОСА ---
    # Меняем цвет при наведении
    current_btn_color = BUTTON_HOVER_COLOR if reset_button_rect.collidepoint(mouse_pos) else BUTTON_COLOR
    
    pygame.draw.rect(screen, current_btn_color, reset_button_rect, border_radius=10)
    reset_text = font_button.render("СБРОСИТЬ ДРАФТ", True, (255, 255, 255))
    text_rect = reset_text.get_rect(center=reset_button_rect.center)
    screen.blit(reset_text, text_rect)

    pygame.display.flip()

pygame.quit()
