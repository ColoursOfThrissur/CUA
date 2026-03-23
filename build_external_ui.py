#!/usr/bin/env python3
"""
Build CUA UI for external deployment
"""
import subprocess
import os
import json
from pathlib import Path

def find_npm():
    """Find npm executable on Windows"""
    # Common npm locations on Windows
    possible_paths = [
        "npm",
        "npm.cmd", 
        "C:\\Program Files\\nodejs\\npm.cmd",
        "C:\\Program Files (x86)\\nodejs\\npm.cmd",
        os.path.expanduser("~\\AppData\\Roaming\\npm\\npm.cmd"),
        os.path.expanduser("~\\AppData\\Local\\npm\\npm.cmd")
    ]
    
    for npm_path in possible_paths:
        try:
            result = subprocess.run([npm_path, "--version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"✓ Found npm at: {npm_path}")
                return npm_path
        except:
            continue
    
    return None

def build_external_ui():
    """Build UI configured for external backend"""
    print("🚀 Building CUA UI for external deployment\n")
    
    # Get backend URL from user
    backend_url = input("Enter your ngrok backend URL (e.g., https://abc123.ngrok.io): ").strip()
    if not backend_url:
        print("❌ Backend URL required")
        return False
    
    if not backend_url.startswith("https://"):
        print("❌ URL must start with https://")
        return False
    
    print(f"✓ Using backend: {backend_url}")
    
    # Create production environment file
    ui_path = Path("ui")
    env_prod_path = ui_path / ".env.production"
    
    env_content = f"""REACT_APP_API_URL={backend_url}
REACT_APP_WS_URL={backend_url.replace('https://', 'wss://')}/ws
GENERATE_SOURCEMAP=false
"""
    
    with open(env_prod_path, 'w') as f:
        f.write(env_content)
    
    print("✓ Created production environment config")
    
    # Find npm command
    npm_cmd = find_npm()
    if not npm_cmd:
        print("❌ npm not found in common locations")
        print("\n🔧 MANUAL BUILD STEPS:")
        print("1. Open new PowerShell as Administrator")
        print("2. cd ui")
        print("3. npm run build")
        print("4. Upload 'build' folder to Vercel/Netlify")
        return False
    
    # Install dependencies if needed
    node_modules = ui_path / "node_modules"
    if not node_modules.exists():
        print("📦 Installing UI dependencies...")
        try:
            subprocess.run([npm_cmd, "install"], cwd=ui_path, check=True)
            print("✓ Dependencies installed")
        except subprocess.CalledProcessError:
            print("❌ Failed to install dependencies")
            return False
    
    # Build for production
    print("🔨 Building production UI...")
    try:
        result = subprocess.run([npm_cmd, "run", "build"], cwd=ui_path, 
                              check=True, capture_output=True, text=True)
        print("✓ Production build completed")
        
        # Show build info
        build_path = ui_path / "build"
        if build_path.exists():
            print(f"📁 Build output: {build_path.absolute()}")
            print("\n🌐 Deployment options:")
            print("1. Upload 'build' folder to Vercel/Netlify")
            print("2. Use 'npx serve build' to test locally")
            print("3. Deploy to any static hosting service")
            
            return True
        else:
            print("❌ Build folder not found")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed: {e}")
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        return False

def create_deployment_instructions():
    """Create deployment instructions"""
    instructions = """
# 🚀 CUA UI Deployment Instructions

## Your UI is now built for external deployment!

### Quick Deploy to Vercel (Recommended):
1. Go to https://vercel.com
2. Sign up/login with GitHub
3. Click "New Project"
4. Upload the 'ui/build' folder
5. Deploy!

### Quick Deploy to Netlify:
1. Go to https://netlify.com
2. Sign up/login
3. Drag & drop the 'ui/build' folder
4. Deploy!

### Test Locally First:
```bash
cd ui
npx serve build
# Test at: http://localhost:3000
```

### What You Get:
- ✅ Full CUA interface accessible from anywhere
- ✅ Connects to your local backend via ngrok
- ✅ Mobile-friendly responsive design
- ✅ Real-time updates via WebSocket
- ✅ All CUA features: chat, tools, evolution, etc.

### Usage:
1. Keep your local backend running: `python start.py`
2. Keep ngrok tunnel running: `ngrok http 8001`
3. Access deployed UI from any device
4. Control your local CUA system remotely!

### Security Notes:
- Only share the UI URL with trusted people
- Your backend is protected by ngrok's random URL
- Stop ngrok tunnel to disable external access
"""
    
    with open("DEPLOYMENT_INSTRUCTIONS.md", "w") as f:
        f.write(instructions)
    
    print("📋 Created DEPLOYMENT_INSTRUCTIONS.md")

if __name__ == "__main__":
    if build_external_ui():
        create_deployment_instructions()
        print("\n🎉 UI ready for external deployment!")
        print("📋 See DEPLOYMENT_INSTRUCTIONS.md for next steps")
    else:
        print("\n❌ Build failed")