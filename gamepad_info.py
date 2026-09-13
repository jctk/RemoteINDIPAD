import pygame

pygame.init()
pygame.joystick.init()

count = pygame.joystick.get_count()

print(f"Number of joysticks: {count}")

for i in range(count):
    js = pygame.joystick.Joystick(i)
    js.init()

    print(f"\n=== GAMEPAD {i} ===")
    print("Joystick system name:", js.get_name())
    print("Instance ID:", js.get_instance_id())

    print("Number of axes:", js.get_numaxes())
    print("Number of buttons:", js.get_numbuttons())
    print("Number of hat controls:", js.get_numhats())
    print("Number of trackballs:", js.get_numballs())