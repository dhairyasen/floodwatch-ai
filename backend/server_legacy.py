import sys
import os

print("\n" + "!" * 80)
print("  WARNING: server_legacy.py is DEPRECATED and has been retired.")
print("  Please run the FastAPI server using uvicorn instead:")
print("  uvicorn main:app --reload")
print("!" * 80 + "\n")
sys.exit(1)

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from flood_analysis import FloodAnalyzer
import ee

backend_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(backend_dir)

print(f"Project directory: {project_dir}")
print(f"Frontend exists: {os.path.exists(os.path.join(project_dir, 'frontend', 'index.html'))}")

# Initialize Earth Engine ONCE when server starts
print("\nInitializing Earth Engine...")
try:
    ee.Initialize(project='flood-analysis-478517')
    print("✓ Earth Engine initialized successfully!")
except Exception as e:
    print(f"⚠ Earth Engine initialization failed: {e}")
    print("Attempting authentication...")
    try:
        ee.Authenticate()
        ee.Initialize(project='flood-analysis-478517')
        print("✓ Earth Engine initialized after authentication!")
    except Exception as auth_error:
        print(f"✗ Authentication failed: {auth_error}")
        print("Please run 'earthengine authenticate' in terminal")

# Create a single analyzer instance
analyzer = FloodAnalyzer()

class Handler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        try:
            # Determine file path
            if self.path == '/' or self.path == '/index.html':
                filepath = os.path.join(project_dir, 'frontend', 'index.html')
                content_type = 'text/html'
            elif self.path == '/styles.css':
                filepath = os.path.join(project_dir, 'frontend', 'styles.css')
                content_type = 'text/css'
            elif self.path == '/script.js':
                filepath = os.path.join(project_dir, 'frontend', 'script.js')
                content_type = 'application/javascript'
            elif self.path.startswith('/outputs/'):
                # Strip query string (cache buster ?t=timestamp)
                clean_path = self.path.split('?')[0]
                filename = clean_path.replace('/outputs/', '')
                filepath = os.path.join(project_dir, 'outputs', filename)
                if filepath.endswith('.png'):
                    content_type = 'image/png'
                elif filepath.endswith('.json'):
                    content_type = 'application/json'
                elif filepath.endswith('.html'):
                    content_type = 'text/html'
                else:
                    content_type = 'text/plain'
            else:
                print(f"404: {self.path}")
                self.send_error(404)
                return
            
            # Check if file exists
            if not os.path.exists(filepath):
                print(f"File not found: {filepath}")
                self.send_error(404)
                return
            
            # Read file
            if content_type == 'image/png':
                with open(filepath, 'rb') as f:
                    content = f.read()
            else:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # Send response
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            
            if isinstance(content, str):
                self.wfile.write(content.encode('utf-8'))
            else:
                self.wfile.write(content)
            
            print(f"200: {self.path}")
            
        except Exception as e:
            print(f"Error: {e}")
            self.send_error(500)
    
    def do_POST(self):
        if self.path == '/analyze':
            try:
                length = int(self.headers['Content-Length'])
                data = json.loads(self.rfile.read(length).decode())
                
                print(f"\nAnalyzing: {data['location']}")
                
                # Use the global analyzer instance with 4 separate dates
                results = analyzer.analyze(
                    data['location'],
                    data['before_start_date'],
                    data['before_end_date'],
                    data['after_start_date'],
                    data['after_end_date'],
                    lat=data.get('lat'),
                    lon=data.get('lon')
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(results).encode())
                
                print("Complete")
                
            except Exception as e:
                print(f"Error: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_error(404)
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def run(port=8000):
    server = HTTPServer(('', port), Handler)
    print(f"\n{'='*50}")
    print(f"🌊 FloodWatch AI Server Running")
    print(f"{'='*50}")
    print(f"Server: http://localhost:{port}")
    print(f"Earth Engine: ✓ Ready")
    print(f"{'='*50}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n🛑 Server Stopped")

if __name__ == '__main__':
    run()