import cv2
import easyocr
import numpy as np

# Path to the uploaded image
IMAGE_PATH = r"C:/Users/vrk17/.gemini/antigravity/brain/ed9d7e1b-4fec-4ae8-9330-0bc58d197e86/uploaded_image_1763892133345.jpg"

def debug_anpr(image_path):
    print(f"Processing: {image_path}")
    reader = easyocr.Reader(['en'], gpu=False)
    
    img = cv2.imread(image_path)
    if img is None:
        print("Failed to load image")
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Define scaling factors
    scales = [1.0, 1.5, 2.0, 2.5]
    
    for scale in scales:
        print(f"\n--- Testing Scale: {scale}x ---")
        try:
            if scale != 1.0:
                width = int(img.shape[1] * scale)
                height = int(img.shape[0] * scale)
                processed_img = cv2.resize(img, (width, height), interpolation=cv2.INTER_CUBIC)
            else:
                processed_img = img.copy()
                
            gray = cv2.cvtColor(processed_img, cv2.COLOR_BGR2GRAY)
            bfilter = cv2.bilateralFilter(gray, 11, 17, 17)
            edged = cv2.Canny(bfilter, 30, 200)
            
            cnts_result = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            contours = cnts_result[0] if len(cnts_result) == 2 else cnts_result[1]
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
            
            location = None
            for contour in contours:
                approx = cv2.approxPolyDP(contour, 10, True)
                if len(approx) == 4:
                    location = approx
                    break
            
            if location is not None:
                mask = np.zeros(gray.shape, np.uint8)
                cv2.drawContours(mask, [location], 0, 255, -1)
                cv2.bitwise_and(processed_img, processed_img, mask=mask)
                (x,y) = np.where(mask==255)
                (x1, y1) = (np.min(x), np.min(y))
                (x2, y2) = (np.max(x), np.max(y))
                input_image = gray[x1:x2+1, y1:y2+1]
            else:
                input_image = gray

            result = reader.readtext(input_image)
            
            detected_text = ""
            for (bbox, text, prob) in result:
                clean = ''.join(e for e in text if e.isalnum()).upper()
                print(f"  Result: '{text}' -> '{clean}' (Prob: {prob:.2f})")
                if len(clean) >= 6:
                    detected_text = clean
                    # Don't break immediately, show all
            
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    debug_anpr(IMAGE_PATH)
