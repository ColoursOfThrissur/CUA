#!/usr/bin/env python3
"""
Build UI with debug information
"""
import subprocess
import os
import json
from pathlib import Path

def build_debug_ui():
    """Build UI with debug logging"""
    print("🔍 Building UI with debug information...")
    
    # Get backend URL
    backend_url = input("Enter your ngrok backend URL: ").strip()
    if not backend_url:
        print("❌ Backend URL required")
        return False
    
    print(f"✓ Using backend: {backend_url}")
    
    # Create production environment file
    ui_path = Path("ui")
    env_prod_path = ui_path / ".env.production"
    
    env_content = f"""REACT_APP_API_URL=/api
REACT_APP_WS_URL=wss://exquisite-quokka-08aa49.netlify.app/ws
GENERATE_SOURCEMAP=true
REACT_APP_DEBUG=true
"""
    
    with open(env_prod_path, 'w') as f:
        f.write(env_content)
    
    print("✓ Created debug production environment config")
    
    # Build for production with source maps
    print("🔨 Building production UI with source maps...")
    try:
        result = subprocess.run(["npm", "run", "build"], cwd=ui_path, 
                              check=True, capture_output=True, text=True)
        print("✓ Production build completed")
        print("📊 Build output:")
        print(result.stdout[-500:])  # Last 500 chars
        
        # Check build folder contents
        build_path = ui_path / "build"
        if build_path.exists():
            print(f"📁 Build output: {build_path.absolute()}")
            
            # List key files
            static_path = build_path / "static"
            if static_path.exists():
                js_files = list((static_path / "js").glob("*.js")) if (static_path / "js").exists() else []
                css_files = list((static_path / "css").glob("*.css")) if (static_path / "css").exists() else []
                
                print(f"📄 JS files: {len(js_files)}")
                print(f"🎨 CSS files: {len(css_files)}")
                
                for css_file in css_files:
                    print(f"   - {css_file.name} ({css_file.stat().st_size} bytes)")
            
            # Check if _redirects and _headers are included
            redirects_file = build_path / "_redirects"
            headers_file = build_path / "_headers"
            
            print(f"🔀 _redirects: {'✓' if redirects_file.exists() else '❌'}")
            print(f"📋 _headers: {'✓' if headers_file.exists() else '❌'}")
            
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

if __name__ == "__main__":
    build_debug_ui()