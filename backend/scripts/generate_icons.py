import os
from PIL import Image, ImageDraw

def create_app_icon(size):
    # Create RGBA canvas
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    scale = size / 512.0
    
    # Outer circle base
    pad = 12 * scale
    draw.ellipse([pad, pad, size - pad, size - pad], fill=(30, 27, 75, 255), outline=(99, 102, 241, 255), width=int(6 * scale))
    
    # Inner dark base
    inner_pad = 24 * scale
    draw.ellipse([inner_pad, inner_pad, size - inner_pad, size - inner_pad], fill=(15, 23, 42, 255))
    
    # Headset arch
    arch_pad = 70 * scale
    draw.arc([arch_pad, arch_pad, size - arch_pad, size - arch_pad], start=190, end=350, fill=(56, 189, 248, 255), width=int(14 * scale))
    
    # Head / Helmet
    hx1, hy1 = 156 * scale, 170 * scale
    hx2, hy2 = 356 * scale, 340 * scale
    draw.rounded_rectangle([hx1, hy1, hx2, hy2], radius=int(45 * scale), fill=(248, 250, 252, 255), outline=(203, 213, 225, 255), width=int(3 * scale))
    
    # Visor screen
    vx1, vy1 = 176 * scale, 195 * scale
    vx2, vy2 = 336 * scale, 295 * scale
    draw.rounded_rectangle([vx1, vy1, vx2, vy2], radius=int(26 * scale), fill=(15, 23, 42, 255))
    
    # Glowing Cyan Eyes (Friendly & Modern)
    ey = 240 * scale
    ex1 = 220 * scale
    ex2 = 292 * scale
    erx = 14 * scale
    ery = 18 * scale
    draw.ellipse([ex1 - erx, ey - ery, ex1 + erx, ey + ery], fill=(34, 211, 238, 255))
    draw.ellipse([ex1 - erx*0.4, ey - ery*0.6, ex1 + erx*0.4, ey - ery*0.1], fill=(255, 255, 255, 255))
    
    draw.ellipse([ex2 - erx, ey - ery, ex2 + erx, ey + ery], fill=(34, 211, 238, 255))
    draw.ellipse([ex2 - erx*0.4, ey - ery*0.6, ex2 + erx*0.4, ey - ery*0.1], fill=(255, 255, 255, 255))
    
    # Smile arc
    sm_pad = 236 * scale
    draw.arc([sm_pad, 250 * scale, (512 - 236) * scale, 275 * scale], start=20, end=160, fill=(34, 211, 238, 255), width=int(4 * scale))
    
    # Ear cushions
    draw.rounded_rectangle([132 * scale, 215 * scale, 160 * scale, 280 * scale], radius=int(10 * scale), fill=(30, 41, 59, 255), outline=(56, 189, 248, 255), width=int(3 * scale))
    draw.rounded_rectangle([352 * scale, 215 * scale, 380 * scale, 280 * scale], radius=int(10 * scale), fill=(30, 41, 59, 255), outline=(168, 85, 247, 255), width=int(3 * scale))
    
    # Microphone arm
    draw.line([(366 * scale, 265 * scale), (360 * scale, 325 * scale), (305 * scale, 330 * scale)], fill=(100, 116, 139, 255), width=int(6 * scale))
    draw.ellipse([293 * scale, 318 * scale, 317 * scale, 342 * scale], fill=(15, 23, 42, 255), outline=(34, 211, 238, 255), width=int(3 * scale))
    draw.ellipse([300 * scale, 325 * scale, 310 * scale, 335 * scale], fill=(34, 211, 238, 255))
    
    # Body neck base
    draw.polygon([
        (180 * scale, 345 * scale),
        (332 * scale, 345 * scale),
        (370 * scale, 410 * scale),
        (142 * scale, 410 * scale)
    ], fill=(15, 23, 42, 255), outline=(51, 65, 85, 255))
    
    # Core indicator light
    draw.rounded_rectangle([232 * scale, 365 * scale, 280 * scale, 373 * scale], radius=int(4 * scale), fill=(34, 211, 238, 255))
    
    return img

def main():
    icons_dir = "backend/app/static/icons"
    os.makedirs(icons_dir, exist_ok=True)
    
    # 512x512
    icon512 = create_app_icon(512)
    icon512.save(os.path.join(icons_dir, "icon-512.png"))
    
    # 192x192
    icon192 = create_app_icon(192)
    icon192.save(os.path.join(icons_dir, "icon-192.png"))
    
    # 180x180 (Apple touch)
    icon180 = create_app_icon(180)
    icon180.save(os.path.join(icons_dir, "apple-touch-icon.png"))
    
    # 64x64 Favicon
    icon64 = create_app_icon(64)
    icon64.save(os.path.join(icons_dir, "favicon.png"))
    icon64.save(os.path.join("backend/app/static", "favicon.ico"), format="ICO")
    
    print("Successfully generated all PWA icons & avatars!")

if __name__ == "__main__":
    main()
