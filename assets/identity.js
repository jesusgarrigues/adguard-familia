(() => {
  'use strict';
  const faces = Array.from({length:12}, (_,i) => ({id:'face-'+String(i+1).padStart(2,'0'),label:'Cara '+(i+1)}));
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
    let value=known(initial)?initial:'';
    const options=[{id:'',label:'Usar inicial'},...faces];
    function setValue(next){value=known(next)?next:'';for(const b of grid.children)b.setAttribute('aria-pressed',String(b.dataset.avatar===value));}
    for(const item of options){const b=document.createElement('button');b.type='button';b.dataset.avatar=item.id;b.className='avatar-option';b.setAttribute('aria-label',item.label);b.title=item.label;
      b.append(avatar({avatar:item.id,username:'A'}));const name=document.createElement('span');name.textContent=item.id?item.label.replace('Cara ',''):'Inicial';b.append(name);
      b.onclick=()=>{setValue(item.id);onChange?.(value);};grid.append(b);
    }
    setValue(value);return {element:root,getValue:()=>value,setValue};
  }
  window.ParentalIdentity={faces,avatar,picker,known};
})();
