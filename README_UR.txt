FRIENDS NET POINT (FNP) BILLING SOFTWARE
========================================

WINDOWS PC PAR CHALANE KA TAREEQA
1. ZIP file ko Extract All karein.
2. Extract folder ko aisi jagah rakhein jahan se delete na ho, misal: Documents\FriendsNetPoint.
3. Python 3 install karein: https://www.python.org/downloads/ (installation mein Add Python to PATH select karein).
4. run_windows.bat par double-click karein. Pehli dafa internet se required packages install honge.
5. Chrome khul kar http://127.0.0.1:5000 par login page kholega.
6. Login: username admin, password ChangeMe123! (agar database pehle se maujood hai to uska password wahi hoga jo aapne set kiya tha).
7. Login ke baad Settings se password change karein.

DESKTOP ICON
Create_Desktop_Shortcut.bat par double-click karein. Desktop par Friends Net Point shortcut ban jayega. Agli dafa shortcut se app launch kar sakte hain.

MOBILE YA DOOSRE PC PAR SAME WI-FI SE
- Jis PC par app chal rahi hai, us PC aur mobile ko same Wi-Fi/router par connect karein.
- Windows mein Command Prompt khol kar ipconfig likhein; Wi-Fi adapter ka IPv4 Address note karein (misal 192.168.1.20).
- Mobile Chrome mein http://192.168.1.20:5000 kholein (apne PC ka asal IP use karein).
- Windows Firewall pooche to sirf Private network par Python access allow karein. Public Wi-Fi par expose na karein.
- PC chalta rehna chahiye aur run_windows.bat wali black window khuli rehni chahiye.

IMPORTANT LIMITATIONS / SECURITY
- Is setup mein mobile/other PC access sirf same local network par hai. Ghar se bahar ya kisi doosre internet connection se use karne ke liye secure hosting, HTTPS, firewall aur production server setup zaroori hai. Port 5000 ko seedha internet par forward na karein.
- App ke database ki backup copy regular banayein. friends_net_point.db file mein records hote hain.
- SMS gateway connected nahi hai. SMS screen abhi actual SMS send nahi karti.
- WhatsApp button message tayyar kar sakta hai, magar user ko WhatsApp se manually send karna hota hai.
- Receipt aur WhatsApp/SMS text par FNP logo add nahi kiya gaya; logo sirf app interface (login/header) par hai.
