(() => {
  'use strict';
  const faces = window.ParentalCatalog.avatars;
  const known = id => faces.some(face => face.id === id);
  function avatar(user, cls='person-avatar') {
    const node=document.createElement(known(user?.avatar)?'img':'span');node.className=cls;
    if(known(user?.avatar)){node.src='/assets/avatars/'+user.avatar+'.svg';node.alt='';node.width=56;node.height=56;}
    else node.textContent=(user?.username||'?').slice(0,1).toUpperCase();
    return node;
  }
  function picker(initial, onChange, label='Elige tu cara') {
    const root=document.createElement('fieldset');root.className='avatar-picker';
    const legend=document.createElement('legend');legend.textContent=label;root.append(legend);
    const grid=document.createElement('div');grid.className='avatar-options';root.append(grid);
    const filters=document.createElement('div');filters.className='catalog-filters';
    const search=document.createElement('input');search.type='search';search.placeholder='Buscar imagen…';search.setAttribute('aria-label','Buscar imagen de usuario');
    const category=document.createElement('select');category.setAttribute('aria-label','Categoría de imágenes');
    for(const group of ['Todas',...new Set(faces.map(item=>item.group))]){const option=document.createElement('option');option.value=group;option.textContent=group;category.append(option);}
    filters.append(search,category);root.insertBefore(filters,grid);
    const count=document.createElement('p');count.className='catalog-count';count.setAttribute('role','status');root.insertBefore(count,grid);
    let value=known(initial)?initial:'';
    const options=[{id:'',label:'Usar inicial'},...faces];
    function setValue(next){value=known(next)?next:'';for(const b of grid.children)b.setAttribute('aria-pressed',String(b.dataset.avatar===value));}
    for(const item of options){const b=document.createElement('button');b.type='button';b.dataset.avatar=item.id;b.className='avatar-option';b.setAttribute('aria-label',item.label);b.title=item.label;
      b.dataset.label=item.label;b.dataset.group=item.group||'';
      const picture=avatar({avatar:item.id,username:'A'});if(picture.tagName==='IMG'){picture.loading='lazy';picture.decoding='async';}b.append(picture);const name=document.createElement('span');name.textContent=item.id?item.label:'Inicial';b.append(name);
      b.onclick=()=>{setValue(item.id);onChange?.(value);};grid.append(b);
    }
    const fold=text=>text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    function filter(){let visible=0;for(const b of grid.children){b.hidden=!!b.dataset.avatar&&((category.value!=='Todas'&&b.dataset.group!==category.value)||!fold(b.dataset.label).includes(fold(search.value)));if(!b.hidden)visible++;}count.textContent=(visible-1)+' imágenes · '+faces.length+' en el catálogo';}
    search.oninput=filter;category.onchange=filter;filter();setValue(value);return {element:root,getValue:()=>value,setValue};
  }
  window.ParentalIdentity={faces,avatar,picker,known};
})();
