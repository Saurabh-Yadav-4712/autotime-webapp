
def test_admin_login(client):
    response = client.post('/login_admin', data={
        'username': 'admin',
        'password': 'password123'
    })
    # Should redirect to admin dashboard
    assert response.status_code == 302
    assert '/admin_dash' in response.location

def test_admin_login_invalid(client):
    response = client.post('/login_admin', data={
        'username': 'admin',
        'password': 'wrongpassword'
    })
    assert response.status_code == 302
    assert '/login' in response.location

def test_protected_route_redirects(client):
    response = client.get('/admin_dash')
    # Should redirect to login since we are not logged in
    assert response.status_code == 302
    assert '/login' in response.location
