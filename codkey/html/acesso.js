(async function() {
  let resposta;
  try {
    resposta = await fetch('/api/sessao');
  } catch (erro) {
    console.error(erro);
    alert('Não foi possível verificar seu acesso. Confira sua conexão.');
    return;
  }
  if (!resposta.ok) {
    window.location.href = 'login.html';
    return;
  }

  const dados = await resposta.json();
  const paginasPermitidas = {
    admin: ['paginainicial.html', 'aluno.html', 'prof.html', 'planos.html', 'pagamentos.html', 'treino.html', 'usuarios.html'],
    professor: ['aluno.html', 'treino.html'],
    aluno: ['planos.html', 'treino.html']
  };
  const navegacao = document.querySelector('.nav-links');
  if (!navegacao) return;

  navegacao.querySelectorAll('a').forEach(link => {
    const pagina = new URL(link.href).pathname.split('/').pop();
    if (pagina === 'login.html') {
      link.dataset.sair = '';
      return;
    }
    link.closest('li').hidden = !paginasPermitidas[dados.usuario.perfil].includes(pagina);
  });

  let sair = navegacao.querySelector('[data-sair]');
  if (!sair) {
    const item = document.createElement('li');
    sair = document.createElement('a');
    sair.href = 'login.html';
    sair.textContent = 'Sair';
    sair.dataset.sair = '';
    item.appendChild(sair);
    navegacao.appendChild(item);
  }

  sair.addEventListener('click', async event => {
    event.preventDefault();
    const respostaLogout = await fetch('/api/logout', { method: 'POST' });
    if (!respostaLogout.ok) {
      alert('Não foi possível encerrar a sessão. Tente novamente.');
      return;
    }
    window.location.href = 'login.html';
  });

  if (dados.usuario.perfil === 'professor' && location.pathname.endsWith('/aluno.html')) {
    document.querySelector('.form-container').hidden = true;
  }
})();
