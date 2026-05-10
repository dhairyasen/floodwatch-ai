CITY_COORDINATES = {
    # Major Metro Cities
    'mumbai': {'lat': 19.0760, 'lon': 72.8777, 'name': 'Mumbai, India'},
    'delhi': {'lat': 28.6139, 'lon': 77.2090, 'name': 'Delhi, India'},
    'bangalore': {'lat': 12.9716, 'lon': 77.5946, 'name': 'Bangalore, India'},
    'hyderabad': {'lat': 17.3850, 'lon': 78.4867, 'name': 'Hyderabad, India'},
    'chennai': {'lat': 13.0827, 'lon': 80.2707, 'name': 'Chennai, India'},
    'kolkata': {'lat': 22.5726, 'lon': 88.3639, 'name': 'Kolkata, India'},
    'ahmedabad': {'lat': 23.0225, 'lon': 72.5714, 'name': 'Ahmedabad, India'},
    'pune': {'lat': 18.5204, 'lon': 73.8567, 'name': 'Pune, India'},
    'surat': {'lat': 21.1702, 'lon': 72.8311, 'name': 'Surat, India'},
    'jaipur': {'lat': 26.9124, 'lon': 75.7873, 'name': 'Jaipur, India'},
    
    # Other Major Cities
    'lucknow': {'lat': 26.8467, 'lon': 80.9462, 'name': 'Lucknow, India'},
    'kanpur': {'lat': 26.4499, 'lon': 80.3319, 'name': 'Kanpur, India'},
    'nagpur': {'lat': 21.1458, 'lon': 79.0882, 'name': 'Nagpur, India'},
    'indore': {'lat': 22.7196, 'lon': 75.8577, 'name': 'Indore, India'},
    'thane': {'lat': 19.2183, 'lon': 72.9781, 'name': 'Thane, India'},
    'bhopal': {'lat': 23.2599, 'lon': 77.4126, 'name': 'Bhopal, India'},
    'visakhapatnam': {'lat': 17.6868, 'lon': 83.2185, 'name': 'Visakhapatnam, India'},
    'pimpri chinchwad': {'lat': 18.6298, 'lon': 73.7997, 'name': 'Pimpri-Chinchwad, India'},
    'patna': {'lat': 25.5941, 'lon': 85.1376, 'name': 'Patna, India'},
    'vadodara': {'lat': 22.3072, 'lon': 73.1812, 'name': 'Vadodara, India'},
    'ghaziabad': {'lat': 28.6692, 'lon': 77.4538, 'name': 'Ghaziabad, India'},
    'ludhiana': {'lat': 30.9010, 'lon': 75.8573, 'name': 'Ludhiana, India'},
    'agra': {'lat': 27.1767, 'lon': 78.0081, 'name': 'Agra, India'},
    'nashik': {'lat': 19.9975, 'lon': 73.7898, 'name': 'Nashik, India'},
    'faridabad': {'lat': 28.4089, 'lon': 77.3178, 'name': 'Faridabad, India'},
    'meerut': {'lat': 28.9845, 'lon': 77.7064, 'name': 'Meerut, India'},
    'rajkot': {'lat': 22.3039, 'lon': 70.8022, 'name': 'Rajkot, India'},
    'varanasi': {'lat': 25.3176, 'lon': 82.9739, 'name': 'Varanasi, India'},
    'srinagar': {'lat': 34.0837, 'lon': 74.7973, 'name': 'Srinagar, India'},
    'amritsar': {'lat': 31.6340, 'lon': 74.8723, 'name': 'Amritsar, India'},
    'allahabad': {'lat': 25.4358, 'lon': 81.8463, 'name': 'Allahabad, India'},
    'ranchi': {'lat': 23.3441, 'lon': 85.3096, 'name': 'Ranchi, India'},
    'howrah': {'lat': 22.5958, 'lon': 88.2636, 'name': 'Howrah, India'},
    'coimbatore': {'lat': 11.0168, 'lon': 76.9558, 'name': 'Coimbatore, India'},
    'jabalpur': {'lat': 23.1815, 'lon': 79.9864, 'name': 'Jabalpur, India'},
    'gwalior': {'lat': 26.2183, 'lon': 78.1828, 'name': 'Gwalior, India'},
    'vijayawada': {'lat': 16.5062, 'lon': 80.6480, 'name': 'Vijayawada, India'},
    'jodhpur': {'lat': 26.2389, 'lon': 73.0243, 'name': 'Jodhpur, India'},
    'madurai': {'lat': 9.9252, 'lon': 78.1198, 'name': 'Madurai, India'},
    'raipur': {'lat': 21.2514, 'lon': 81.6296, 'name': 'Raipur, India'},
    'kota': {'lat': 25.2138, 'lon': 75.8648, 'name': 'Kota, India'},
    'chandigarh': {'lat': 30.7333, 'lon': 76.7794, 'name': 'Chandigarh, India'},
    'guwahati': {'lat': 26.1445, 'lon': 91.7362, 'name': 'Guwahati, India'},
    'mysore': {'lat': 12.2958, 'lon': 76.6394, 'name': 'Mysore, India'},
    'thiruvananthapuram': {'lat': 8.5241, 'lon': 76.9366, 'name': 'Thiruvananthapuram, India'},
    'bareilly': {'lat': 28.3670, 'lon': 79.4304, 'name': 'Bareilly, India'},
    'moradabad': {'lat': 28.8389, 'lon': 78.7378, 'name': 'Moradabad, India'},
    'tiruchirappalli': {'lat': 10.7905, 'lon': 78.7047, 'name': 'Tiruchirappalli, India'},
    'salem': {'lat': 11.6643, 'lon': 78.1460, 'name': 'Salem, India'},
    'tiruppur': {'lat': 11.1085, 'lon': 77.3411, 'name': 'Tiruppur, India'},
    
    # Coastal Cities (flood-prone)
    'kochi': {'lat': 9.9312, 'lon': 76.2673, 'name': 'Kochi, India'},
    'mangalore': {'lat': 12.9141, 'lon': 74.8560, 'name': 'Mangalore, India'},
    'puducherry': {'lat': 11.9416, 'lon': 79.8083, 'name': 'Puducherry, India'},
}

BUFFER_DISTANCE = 50000
CLOUD_THRESHOLD = 80
SCALE = 10

SEVERITY_THRESHOLDS = {
    'low': 10,
    'medium': 50,
    'high': 100,
    'critical': 200
}

NDWI_THRESHOLD = 0.0
MNDWI_THRESHOLD = 0.0

POPULATION_DENSITY = {
    'mumbai': 20000, 'delhi': 11000, 'bangalore': 11000, 'hyderabad': 18000,
    'chennai': 26000, 'kolkata': 24000, 'ahmedabad': 12000, 'pune': 6000,
    'surat': 13000, 'jaipur': 6000, 'lucknow': 7000, 'kanpur': 10000,
    'nagpur': 4000, 'indore': 6000, 'thane': 19000, 'bhopal': 3000,
    'visakhapatnam': 6000, 'patna': 13000, 'vadodara': 5000, 'ghaziabad': 8000,
    'ludhiana': 7000, 'agra': 9000, 'nashik': 5000, 'varanasi': 8000,
}